import io
import json
import logging
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
from types import SimpleNamespace
from typing import Any

import pytest

from boss_screen import ai as ai_mod
from boss_screen import run as run_mod
from boss_screen import watch as watch_mod
from boss_screen.ai import AiError, complete
from boss_screen.browser import open_chrome, risk_state
from boss_screen.cards import Card, ingest_job_list, parse_detail
from boss_screen.page_facts import (
    REQUEST_FAILURE_STREAK,
    ApiError,
    PageFacts,
    business_data,
)
from boss_screen.run import (
    AI_BREAKER_MIN_SAMPLES,
    MAX_DETERMINISTIC_AI_FAILS,
    KeywordStats,
    Session,
    _landed,
)
from boss_screen.store import JobStore
from boss_screen.watch import _last_run, watch_log

URL = "https://www.zhipin.com/web/geek/jobs?city=101210100&query=Agent"
LIST = "https://www.zhipin.com/wapi/zpgeek/search/joblist.json"
DETAIL = "https://www.zhipin.com/wapi/zpgeek/job/detail.json"


def detail(ident="one", code=0):
    return json.dumps({"code": code, "zpData": {
        "jobInfo": {"encryptId": ident, "jobName": "Agent开发", "postDescription": "负责工具调用", "locationName": "杭州"},
        "brandComInfo": {"brandName": "甲"},
        "bossInfo": {"activeTimeDesc": "刚刚活跃", "name": "王", "title": "工程师"},
    }})


def listing(*, more=False, items=None, code=0):
    return json.dumps({"code": code, "zpData": {
        "hasMore": more, "jobList": items if items is not None else [{
            "encryptJobId": "one", "jobName": "Agent开发", "brandName": "甲", "cityName": "杭州",
            "salaryDesc": "200-300元/天", "skills": ["RAG"], "bossTitle": "工程师",
        }],
    }})


class Page:
    def __init__(self):
        self.url = URL
        self.callbacks = {}
        self.dom = []
        self.tick = lambda: None
        self.read_error = False

    def on(self, event, callback):
        self.callbacks[event] = callback

    def locator(self, _selector):
        if self.read_error:
            raise RuntimeError("Target closed")
        return SimpleNamespace(count=lambda: 0)

    def evaluate(self, _js):
        return self.dom

    def wait_for_timeout(self, _ms):
        self.tick()


def respond(facts, body, url=LIST, status=200, request=None):
    if request is None:
        request = SimpleNamespace(url=url, method="POST" if url == LIST else "GET")
        facts.on_request(request)
    facts.on_response(SimpleNamespace(url=url, status=status, request=request, text=lambda: body))


@pytest.fixture
def session(tmp_path):
    rules = dict(black_jobs=[], black_companies=[], black_recruiters=[], company_tokens=[], job_tokens=[])
    settings: Any = SimpleNamespace(detail_limit=-1, stop_on_risk=False, black_recruiters=[], rule_kwargs=lambda: rules)
    store = JobStore(tmp_path / "boss.db")
    s: Any = Session(settings, store, Page(), threading.Event())
    s.target_url = URL
    s._pause_between_jobs = lambda: None
    yield s
    store.close()


@pytest.mark.parametrize("body,status", [
    ('{"code":37,"zpData":{}}', 200), ('{"code":0,"zpData":{}}', 200),
    (listing(), 429), ("<html>login</html>", 200), (listing(more=True, items=[]), 200),
    (listing(items=[{}]), 200),
])
def test_first_bad_list_response_records_fault_instead_of_end(body, status):
    facts = PageFacts(Page())
    respond(facts, body, status=status)
    assert facts.fault is not None
    assert facts.has_more is None
    assert not facts.cards


def test_successful_empty_list_confirms_end():
    facts = PageFacts(Page())
    respond(facts, listing(items=[]))
    assert facts.fault is None
    assert facts.has_more is False
    assert facts.list_serial > 0


def test_nonzero_business_code_does_not_produce_jobs_or_detail():
    assert ingest_job_list(listing(code=37)) == []
    assert not parse_detail(detail(code=37))["jd"]


def test_detail_parser_keeps_response_identity():
    assert parse_detail(detail())["encryptId"] == "one"


def test_response_from_previous_keyword_is_ignored():
    facts = PageFacts(Page())
    request = SimpleNamespace(url=LIST)
    facts.on_request(request)
    facts.reset()
    respond(facts, listing(), request=request)
    assert facts.list_serial == 0
    assert not facts.cards


def test_single_request_failure_is_noise_until_requests_keep_failing():
    facts = PageFacts(Page())
    request = SimpleNamespace(url=DETAIL)
    facts.on_request(request)
    facts.on_failed(request)
    assert facts.fault is None

    for _ in range(REQUEST_FAILURE_STREAK - 1):
        request = SimpleNamespace(url=DETAIL)
        facts.on_request(request)
        facts.on_failed(request)
    assert facts.fault is not None
    assert facts.fault.kind == "detail"
    assert facts.fault.retryable is True


def test_successful_response_resets_the_request_failure_streak():
    facts = PageFacts(Page())
    for _ in range(REQUEST_FAILURE_STREAK - 1):
        request = SimpleNamespace(url=LIST)
        facts.on_request(request)
        facts.on_failed(request)
    respond(facts, listing())
    request = SimpleNamespace(url=LIST)
    facts.on_request(request)
    facts.on_failed(request)
    assert facts.fault is None


def test_dom_before_api_is_processed_only_with_full_list_facts(session):
    session.page.dom = [{"href": "/job_detail/one.html", "job": "Agent开发", "salary": "\ue033\ue031元/天"}]
    handled = set()
    assert session._harvest_new(handled) == []
    assert not handled
    respond(session.facts, listing())
    batch = session._harvest_new(handled)
    assert batch[0].salary == "200-300元/天"
    assert batch[0].tags == "RAG"
    assert handled == {"one"}


def test_api_card_survives_virtual_unmount_and_missing_target_stays_pending(session):
    respond(session.facts, listing())
    handled = set()
    batch = session._harvest_new(handled)
    session._card_locator = lambda _id: None
    with ThreadPoolExecutor(1) as pool:
        session._click_details("Agent", batch, pool, [])
    assert session.detail_attempts == 0
    assert session._harvest_new(handled)[0].encrypt_id == "one"
    assert session.pending_cards


def test_automatic_first_detail_is_consumed_without_click(session):
    session.store.upsert({"encryptId": "one", "job": "Agent开发", "company": "甲", "stage": "jd_queued"})
    respond(session.facts, detail(), DETAIL)
    session._card_locator = lambda _id: pytest.fail("cached detail must not click")
    futures = []
    session._screen_job = lambda _kw, _job: "ai_keep"
    stats = KeywordStats()
    with ThreadPoolExecutor(1) as pool:
        session._click_details("Agent", [Card(encrypt_id="one")], pool, futures, stats)
    assert session.detail_attempts == 0
    assert stats.detail_ok == 1
    assert session.store.get("one")["jd"] == "负责工具调用"


def test_detail_identity_does_not_follow_stale_dom_and_rejects_wrong_response(session):
    card = Card(encrypt_id="one")
    assert session._job_from_detail(card, detail("two")) is None
    job = session._job_from_detail(card, detail())
    assert job["encryptId"] == "one"
    assert job["href"].endswith("/one.html")


def test_click_consumes_limit_once_and_stores_only_target_response(session):
    session.store.upsert({"encryptId": "one", "job": "Agent开发", "company": "甲", "stage": "jd_queued"})
    session._card_locator = lambda _id: object()
    def click(_target):
        respond(session.facts, detail("two"), DETAIL)
        respond(session.facts, detail(), DETAIL)
        return True
    session._human_click = click
    session._screen_job = lambda _kw, _job: "ai_keep"
    with ThreadPoolExecutor(1) as pool:
        session._click_details("Agent", [Card(encrypt_id="one")], pool, [])
        session._click_details("Agent", [Card(encrypt_id="one")], pool, [])
    assert session.detail_attempts == 1
    assert session.store.get("two") is None
    assert session.store.get("one")["jd"]


def test_stop_during_preclick_sleep_prevents_click(session):
    clicked = []
    target = SimpleNamespace(
        scroll_into_view_if_needed=lambda **_kw: None,
        bounding_box=lambda: {"width": 100, "height": 20},
        hover=lambda **_kw: None, click=lambda **_kw: clicked.append(True),
    )
    session._sleep = lambda _seconds: session.stop.set() or True
    assert session._human_click(target) is False
    assert not clicked


def test_click_exception_is_not_counted_as_detail_timeout_or_reclicked(session):
    session._card_locator = lambda _id: object()
    def click(_target):
        raise RuntimeError("covered")
    session._human_click = click
    def pause(_reason):
        if session.facts.fault:
            session.stop.set()
            return True
        return False
    session._halt = pause
    with ThreadPoolExecutor(1) as pool:
        session._click_details("Agent", [Card(encrypt_id="one")], pool, [])
    assert session.detail_attempts == 0
    assert session.facts.fault.kind == "detail"


def test_unknown_fault_needs_explicit_resume_even_after_success(session):
    session.facts.fail("业务码37")
    ticks = []
    def tick():
        ticks.append(1)
        if len(ticks) == 1:
            respond(session.facts, listing())
        elif len(ticks) == 2:
            assert session.facts.fault is not None
            session.resume.set()
    session.page.tick = tick
    assert session._halt("异常") is False
    assert len(ticks) == 2
    assert session.facts.fault is None


@pytest.fixture
def clock(session, monkeypatch):
    now = SimpleNamespace(seconds=0.0)
    monkeypatch.setattr(run_mod.time, "monotonic", lambda: now.seconds)

    def wait(ms):
        now.seconds += ms / 1000
        session.page.tick()

    session.page.wait_for_timeout = wait
    return now


def test_auto_recovery_has_no_human_alert_and_watch_accepts_completion(session, clock, caplog, tmp_path):
    session.facts.fail("网络失败", retryable=True)
    reloads = []

    def goto(url):
        reloads.append(url)
        respond(session.facts, listing())

    session._goto = goto
    with caplog.at_level(logging.INFO, logger="boss_screen"):
        assert session._halt("异常") is False
    messages = [record.message for record in caplog.records]
    assert reloads == [URL]
    assert not any("暂停等人" in message for message in messages)
    assert any("目标业务已恢复，继续" in message for message in messages)
    p = tmp_path / "recovery.log"
    p.write_text("INFO 流式筛选开始\n" + "\n".join(messages) + "\nINFO 筛选结果：完成\n")
    assert watch_log(p, lambda: False, out=io.StringIO()) == 0


def test_watch_stays_attached_during_automatic_recovery(tmp_path):
    p = tmp_path / "screen.log"
    chunks = iter([
        ("INFO 流式筛选开始\nINFO 自动恢复中：网络失败\n", True),
        ("INFO 目标业务已恢复，继续\n", True),
        ("INFO 筛选结果：完成\n", False),
    ])

    def alive():
        text, running = next(chunks)
        with p.open("a") as handle:
            handle.write(text)
        return running

    assert watch_log(p, alive, poll_seconds=0, out=io.StringIO()) == 0


def test_exhausted_automatic_recovery_alerts_watch_only_after_last_response_wait(session, clock, caplog, tmp_path):
    session.facts.fail("网络失败", retryable=True)
    reloads = []
    session._goto = lambda url: reloads.append(url)
    deadline = run_mod.SELF_RECOVERY_INTERVAL_SECONDS * (run_mod.MAX_SELF_RECOVERY_ATTEMPTS + 1)
    session.page.tick = lambda: session.stop.set() if clock.seconds > deadline + 1 else None
    with caplog.at_level(logging.INFO, logger="boss_screen"):
        assert session._halt("异常") is True
    messages = [record.message for record in caplog.records]
    alert_index = next(i for i, message in enumerate(messages) if "暂停等人" in message)
    attempts_before_alert = [message for message in messages[:alert_index] if "重新加载目标页" in message]
    assert len(attempts_before_alert) == run_mod.MAX_SELF_RECOVERY_ATTEMPTS
    assert len(reloads) == run_mod.MAX_SELF_RECOVERY_ATTEMPTS
    p = tmp_path / "exhausted.log"
    p.write_text("\n".join(messages) + "\n")
    assert watch_log(p, lambda: True, out=io.StringIO()) == 2


def test_verification_appearing_during_recovery_is_not_reloaded(session, clock, caplog):
    session.facts.fail("网络失败", retryable=True)
    reloads = []
    session._goto = lambda _url: reloads.append(session.page.url)
    restored = False

    def tick():
        nonlocal restored
        if reloads and clock.seconds < 80:
            session.page.url = "https://www.zhipin.com/web/user/safe/verify-slider"
        elif clock.seconds >= 80 and not restored:
            session.page.url = URL
            respond(session.facts, listing())
            restored = True
        if clock.seconds > 100:
            session.stop.set()

    session.page.tick = tick
    with caplog.at_level(logging.INFO, logger="boss_screen"):
        assert session._halt("异常") is False
    assert reloads == [URL]
    assert any("暂停等人" in record.message for record in caplog.records)
    assert session.facts.fault is None


def test_title_breaker_saves_finished_results_and_does_not_start_remaining_cards(session, monkeypatch):
    monkeypatch.setattr(run_mod, "AI_PARALLELISM", 1)
    session.settings.title_prompt = "提示词"
    session._sleep = lambda _seconds: False
    session._click_details = lambda *_args: pytest.fail("熔断后不能再点击")
    calls = []

    def reply(*_args):
        calls.append(1)
        if len(calls) == 1:
            return '{"action":"park","reason":"需进一步判断"}'
        raise AiError("401 未授权", status=401)

    monkeypatch.setattr(run_mod, "complete", reply)
    cards = [Card(encrypt_id=f"job{i}", job="Python开发", company="甲", area="杭州") for i in range(8)]
    with ThreadPoolExecutor(1) as pool:
        session._process_batch("Agent", cards, 0, pool, [])
    assert session.stop.is_set()
    assert len(calls) == 4
    assert session.store.get("job0")["stage"] == "jd_park"
    assert all(session.store.get(f"job{i}")["stage"] == "ai_title_pending" for i in range(1, 4))
    assert all(session.store.get(f"job{i}") is None for i in range(4, 8))


def test_title_success_finishing_after_stop_is_still_saved(session, monkeypatch):
    monkeypatch.setattr(run_mod, "AI_PARALLELISM", 2)
    session.settings.title_prompt = "{job}"
    session._sleep = lambda _seconds: False
    session._click_details = lambda *_args: pytest.fail("停止后不能再点击")
    started = threading.Event()
    released = threading.Event()

    def reply(_settings, prompt):
        if prompt == "Python开发":
            started.set()
            assert released.wait(2)
            return '{"action":"drop","reason":"不匹配"}'
        assert started.wait(2)
        session.stop.set()
        released.set()
        raise AiError("401 未授权", status=401)

    monkeypatch.setattr(run_mod, "complete", reply)
    cards = [Card(encrypt_id="slow", job="Python开发", company="甲"), Card(encrypt_id="fast", job="AI开发", company="乙")]
    with ThreadPoolExecutor(1) as pool:
        session._process_batch("Agent", cards, 0, pool, [])
    assert session.store.get("slow")["stage"] == "ai_title_drop"
    assert session.store.get("fast")["stage"] == "ai_title_pending"


def test_missing_detail_after_list_recovery_is_deferred_and_next_card_is_processed(session, clock, monkeypatch):
    cards = [Card(encrypt_id=ident, job="Python开发", company="甲", area="杭州") for ident in ("one", "two")]
    for card in cards:
        session._write_card("Agent", card, "jd_queued", "标题可点")
    clicked = []
    session._card_locator = lambda ident: ident

    def click(ident):
        clicked.append(ident)
        if ident == "two":
            respond(session.facts, detail(ident), DETAIL)
        return True

    def goto(_url):
        respond(session.facts, listing(more=True))
        respond(session.facts, detail("other"), DETAIL)

    session._human_click = click
    session._goto = goto
    monkeypatch.setattr(run_mod, "jd_prompt", lambda *_args: "提示词")
    monkeypatch.setattr(run_mod, "complete", lambda *_args: '{"keep":true,"reason":"匹配"}')
    stats = KeywordStats()
    with ThreadPoolExecutor(1) as pool:
        session._click_details("Agent", cards, pool, [], stats)
        assert clicked == ["one", "two"]
        session._click_details("Agent", cards, pool, [])
    assert clicked == ["one", "two"]
    deferred = session.store.get("one")
    assert deferred["stage"] == "jd_queued"
    assert not deferred["jd"]
    assert "下轮" in deferred["reason"]
    assert session.store.get("two")["stage"] == "ai_keep"
    assert session.store.get("other") is None
    assert stats.detail_fail == 1
    assert stats.detail_ok == 1
    assert not session.pending_cards
    assert not session.stop.is_set()


def test_detail_arriving_during_recovery_inside_a_sleep_is_saved(session, clock, monkeypatch):
    card = Card(encrypt_id="one", job="Python开发", company="甲", area="杭州")
    session._write_card("Agent", card, "jd_queued", "标题可点")
    session._card_locator = lambda _ident: object()

    def click(_target):
        request = SimpleNamespace(url=DETAIL)
        session.facts.on_request(request)
        session.facts.on_failed(request)
        return True

    reloads = []

    def goto(url):
        reloads.append(url)
        respond(session.facts, listing())
        respond(session.facts, detail(), DETAIL)

    session._human_click = click
    session._goto = goto
    monkeypatch.setattr(run_mod, "jd_prompt", lambda *_args: "提示词")
    monkeypatch.setattr(run_mod, "complete", lambda *_args: '{"keep":true,"reason":"匹配"}')
    stats = KeywordStats()
    with ThreadPoolExecutor(1) as pool:
        session._click_details("Agent", [card], pool, [], stats)
    assert reloads == [URL]
    assert session.store.get("one")["stage"] == "ai_keep"
    assert session.store.get("one")["jd"]
    assert stats.detail_ok == 1
    assert stats.detail_fail == 0
    assert session.detail_attempts == 1


def test_single_failed_list_request_without_followup_gets_automatic_recovery(session, clock):
    respond(session.facts, listing(more=True))
    request = SimpleNamespace(url=LIST)
    session.facts.on_request(request)
    session.facts.on_failed(request)
    assert session.facts.fault is None
    clock.seconds = 10
    reloads = []

    def goto(url):
        reloads.append(url)
        respond(session.facts, listing())

    session._goto = goto
    assert session._halt("滚动期间检查") is False
    assert reloads == [URL]
    assert session.facts.fault is None


def test_single_failed_request_recovers_through_the_streaming_loop(session, clock, caplog):
    respond(session.facts, listing(more=True))
    request = SimpleNamespace(url=LIST)
    session.facts.on_request(request)
    session.facts.on_failed(request)
    session.page.mouse = SimpleNamespace(wheel=lambda *_args: None)
    session.page.tick = lambda: session.stop.set() if clock.seconds > 100 else None
    session._process_batch = lambda _kw, _cards, seen, *_args: seen
    reloads = []

    def goto(url):
        reloads.append(url)
        respond(session.facts, listing(items=[]))

    session._goto = goto
    with caplog.at_level(logging.INFO, logger="boss_screen"):
        session._stream_list("Agent")
    assert reloads == [URL]
    assert not session.stop.is_set()
    assert session.facts.fault is None
    assert not any("暂停等人" in record.message for record in caplog.records)


def test_late_success_after_the_last_reload_does_not_raise_a_human_alert(session, clock, caplog):
    session.facts.fail("网络失败", retryable=True)
    attempts = []
    session._goto = lambda _url: attempts.append(clock.seconds)

    def tick():
        if len(attempts) == run_mod.MAX_SELF_RECOVERY_ATTEMPTS and clock.seconds >= attempts[-1] + 1:
            respond(session.facts, listing())
        if clock.seconds > 200:
            session.stop.set()

    session.page.tick = tick
    with caplog.at_level(logging.INFO, logger="boss_screen"):
        assert session._halt("异常") is False
    assert len(attempts) == run_mod.MAX_SELF_RECOVERY_ATTEMPTS
    assert not any("暂停等人" in record.message for record in caplog.records)


def test_recovered_transient_fault_before_first_reload_needs_no_signal(session, clock, caplog):
    session.facts.fail("网络失败", retryable=True)
    respond(session.facts, listing())
    session._goto = lambda _url: pytest.fail("已有新的成功响应，不应再重载")
    with caplog.at_level(logging.INFO, logger="boss_screen"):
        assert session._halt("异常") is False
    assert any("目标业务已恢复，继续" in record.message for record in caplog.records)


def test_unrelated_detail_success_does_not_hide_a_failed_list_request(session, clock):
    request = SimpleNamespace(url=LIST)
    session.facts.on_request(request)
    session.facts.on_failed(request)
    respond(session.facts, detail(), DETAIL)
    clock.seconds = 10
    reloads = []

    def goto(url):
        reloads.append(url)
        respond(session.facts, listing())

    session._goto = goto
    assert session._halt("列表检查") is False
    assert reloads == [URL]


def test_matching_success_during_debounce_avoids_reloading(session, clock):
    request = SimpleNamespace(url=LIST)
    session.facts.on_request(request)
    session.facts.on_failed(request)
    clock.seconds = 1
    respond(session.facts, listing())
    clock.seconds = 10
    session._goto = lambda _url: pytest.fail("业务已自行恢复，不应重载")
    assert session._halt("检查") is False
    assert session.facts.fault is None


def test_stale_request_failure_does_not_trigger_recovery_in_next_keyword(session, clock):
    request = SimpleNamespace(url=LIST)
    session.facts.on_request(request)
    session.facts.reset()
    session.facts.on_failed(request)
    clock.seconds = 10
    session._goto = lambda _url: pytest.fail("旧关键词的请求失败不能重载新关键词")
    assert session._halt("检查") is False
    assert session.facts.fault is None


def test_retryable_network_noise_does_not_overwrite_an_ip_risk_fault(session):
    respond(session.facts, json.dumps({"code": 35, "message": "IP异常", "zpData": {}}))
    for _ in range(REQUEST_FAILURE_STREAK):
        request = SimpleNamespace(url=LIST)
        session.facts.on_request(request)
        session.facts.on_failed(request)
    assert "35" in session.facts.fault.reason
    assert not session.facts.fault.retryable


def test_retryable_fault_self_recovers_without_waiting_for_a_human(session, monkeypatch, caplog):
    session.facts.fail("岗位接口网络请求失败", "list", retryable=True)
    monkeypatch.setattr(run_mod, "SELF_RECOVERY_INTERVAL_SECONDS", 0.0)
    reloads = []

    def goto(url):
        reloads.append(url)
        respond(session.facts, listing())

    monkeypatch.setattr(session, "_goto", goto)
    with caplog.at_level(logging.INFO, logger="boss_screen"):
        assert session._halt("异常") is False
    assert reloads == [URL]
    assert session.facts.fault is None
    assert any("目标业务已恢复，继续" in record.message for record in caplog.records)


def test_self_recovery_stops_after_the_attempt_budget(session, monkeypatch):
    session.facts.fail("岗位接口网络请求失败", "list", retryable=True)
    monkeypatch.setattr(run_mod, "SELF_RECOVERY_INTERVAL_SECONDS", 0.0)
    reloads = []
    monkeypatch.setattr(session, "_goto", lambda url: reloads.append(url))
    ticks = []

    def tick():
        ticks.append(1)
        if len(ticks) == 8:
            session.resume.set()
            respond(session.facts, listing())

    session.page.tick = tick
    assert session._halt("异常") is False
    assert len(reloads) == run_mod.MAX_SELF_RECOVERY_ATTEMPTS


def test_verification_fault_never_self_reloads(session, monkeypatch):
    monkeypatch.setattr(run_mod, "SELF_RECOVERY_INTERVAL_SECONDS", 0.0)
    reloads = []
    monkeypatch.setattr(session, "_goto", lambda url: reloads.append(url))
    respond(session.facts, json.dumps({"code": 31, "message": "请完成验证", "zpData": {}}))
    ticks = []

    def tick():
        ticks.append(1)
        if len(ticks) == 1:
            session.resume.set()
            respond(session.facts, listing())

    session.page.tick = tick
    assert session._halt("异常") is False
    assert reloads == []


def test_ip_risk_code_pauses_with_the_server_message_and_no_reload(session, monkeypatch, caplog):
    monkeypatch.setattr(run_mod, "SELF_RECOVERY_INTERVAL_SECONDS", 0.0)
    reloads = []
    monkeypatch.setattr(session, "_goto", lambda url: reloads.append(url))
    respond(session.facts, json.dumps({"code": 35, "message": "您的IP地址存在异常行为.", "zpData": {}}))
    fault = session.facts.fault
    assert fault is not None
    assert fault.verification is False
    assert fault.retryable is False
    ticks = []

    def tick():
        ticks.append(1)
        if len(ticks) == 1:
            session.resume.set()
            respond(session.facts, listing())

    session.page.tick = tick
    with caplog.at_level(logging.WARNING, logger="boss_screen"):
        assert session._halt("异常") is False
    assert reloads == []
    assert any(
        "您的IP地址存在异常行为." in record.message and "出口 IP" in record.message
        for record in caplog.records
    )


def test_title_ai_trips_the_circuit_on_deterministic_failures(session, monkeypatch):
    monkeypatch.setattr(run_mod, "title_prompt", lambda *_a, **_k: "提示词")
    monkeypatch.setattr(run_mod, "complete", _ai_deterministic_boom)
    cards = [Card(encrypt_id=f"c{i}", job="开发", company="甲") for i in range(MAX_DETERMINISTIC_AI_FAILS)]
    session._title_ai("Agent", cards)
    assert session.stop.is_set()
    assert session.end_reason == "熔断"


def test_unparsable_title_reply_is_retryable_and_does_not_trip(session, monkeypatch):
    monkeypatch.setattr(run_mod, "title_prompt", lambda *_a, **_k: "提示词")
    monkeypatch.setattr(run_mod, "complete", lambda *_a, **_k: "这不是 JSON")
    cards = [Card(encrypt_id="c1", job="开发", company="甲")]
    assert session._title_ai("Agent", cards) == [(None, "这不是 JSON")]
    assert not session.stop.is_set()
    assert session.ai_deterministic_fails == 0


def test_verification_disappearing_without_business_does_not_resume(session):
    session.page.url = "https://www.zhipin.com/web/user/safe/verify-slider"
    ticks = []
    def tick():
        ticks.append(1)
        session.page.url = URL
        if len(ticks) == 2:
            respond(session.facts, listing())
    session.page.tick = tick
    assert session._halt("验证") is False
    assert len(ticks) == 2


def test_wrong_job_success_does_not_recover_target_detail(session):
    session.target_detail = "one"
    session.facts.fail("详情失败", "detail", True)
    ticks = []
    def tick():
        ticks.append(1)
        respond(session.facts, detail("two" if len(ticks) == 1 else "one"), DETAIL)
    session.page.tick = tick
    assert session._halt("详情") is False
    assert len(ticks) == 2


def test_stop_on_risk_sets_circuit_result_on_first_error(session):
    session.settings.stop_on_risk = True
    session.facts.fail("HTTP 429")
    assert session._halt("异常") is True
    assert session.end_reason == "熔断"
    assert session.stop.is_set()


def test_dom_read_failure_is_unknown_instead_of_safe():
    page = Page()
    page.read_error = True
    assert risk_state(page) is None


@pytest.mark.parametrize("path", ["/web/common/403.html?code=31", "/web/user/safe/verify-slider"])
def test_block_urls_are_detected(path):
    page = Page()
    page.url = "https://www.zhipin.com" + path
    assert risk_state(page) is True


def test_landing_on_old_keyword_does_not_count_as_target():
    page = Page()
    assert not _landed(page, URL.replace("Agent", "RAG"))
    assert _landed(page, URL)


def _ai_deterministic_boom(*_args, **_kwargs):
    raise AiError("AI请求失败，状态码: 401, 详情: 未授权", retryable=False, status=401)


def test_deterministic_jd_failures_trip_the_circuit_while_browsing(session, monkeypatch):
    monkeypatch.setattr(run_mod, "jd_prompt", lambda *_a, **_k: "提示词")
    monkeypatch.setattr(run_mod, "complete", _ai_deterministic_boom)
    with ThreadPoolExecutor(1) as pool:
        for _ in range(MAX_DETERMINISTIC_AI_FAILS):
            session._submit_jd(pool, "Agent", {"encryptId": "one", "company": "甲", "job": "开发"}).result()
    assert session.stop.is_set()
    assert session.end_reason == "熔断"


def test_pending_jd_retry_uses_the_same_circuit(session, monkeypatch):
    monkeypatch.setattr(run_mod, "jd_prompt", lambda *_a, **_k: "提示词")
    monkeypatch.setattr(run_mod, "complete", _ai_deterministic_boom)
    session.store.pending_jd_rows = lambda: [{"keyword": "Agent"}] * 5
    session._retry_pending_jds()
    assert session.stop.is_set()
    assert session.ai_deterministic_fails >= MAX_DETERMINISTIC_AI_FAILS


def test_deterministic_ai_failures_trip_at_once_but_retryable_ones_do_not(session):
    for _ in range(MAX_DETERMINISTIC_AI_FAILS - 1):
        session._record_ai(False)
    assert not session.stop.is_set()
    session._record_ai(False)
    assert session.stop.is_set()
    assert session.end_reason == "熔断"


def test_retryable_ai_failures_spread_across_successes_do_not_trip(session):
    for _ in range(20):
        session._record_ai(False, retryable=True)
        session._record_ai(True)
    assert not session.stop.is_set()


def test_sustained_retryable_ai_failures_still_trip_the_window(session):
    for _ in range(AI_BREAKER_MIN_SAMPLES - 1):
        session._record_ai(False, retryable=True)
    assert not session.stop.is_set()
    session._record_ai(False, retryable=True)
    assert session.stop.is_set()
    assert session.end_reason == "熔断"


@pytest.mark.parametrize("code,verification", [(31, True), (35, False), (36, True), (37, True)])
def test_risk_codes_carry_the_server_message_and_a_hint(code, verification):
    body = json.dumps({"code": code, "message": "您的IP地址存在异常行为.", "zpData": {}})
    with pytest.raises(ApiError) as caught:
        business_data(body)
    assert str(caught.value) == f"岗位接口业务码 {code}（您的IP地址存在异常行为.）"
    assert caught.value.hint
    assert caught.value.verification is verification
    assert caught.value.retryable is False


def test_business_code_without_message_and_http_5xx_classification():
    with pytest.raises(ApiError) as caught:
        business_data('{"code":37,"zpData":{}}')
    assert str(caught.value) == "岗位接口业务码 37"
    assert "环境" in caught.value.hint
    with pytest.raises(ApiError) as overloaded:
        business_data("<html>502</html>", 502)
    assert overloaded.value.retryable is True


def test_429_reply_waits_the_gateway_cooldown_then_retries(monkeypatch):
    calls = []
    slept: list[float] = []
    reply = json.dumps({"choices": [{"message": {"content": '{"action": "drop", "reason": "不匹配"}'}}]}).encode()

    class Ok:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return reply

    def urlopen(_request, timeout=0):
        calls.append(timeout)
        if len(calls) == 1:
            detail = json.dumps({"error": {"reset_seconds": 4}}).encode()
            raise urllib.error.HTTPError("http://ai", 429, "too many requests", Message(), io.BytesIO(detail))
        return Ok()

    monkeypatch.setattr(ai_mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(ai_mod.time, "sleep", slept.append)
    settings: Any = SimpleNamespace(ai_base="http://127.0.0.1:8317/v1", ai_model="m", ai_key="k")
    assert "drop" in complete(settings, "提示词")
    assert len(slept) == 1
    assert 4.0 <= slept[0] <= ai_mod.AI_MAX_COOLDOWN_SECONDS


def test_http_4xx_client_error_is_not_retried(monkeypatch):
    calls = []

    def urlopen(_request, timeout=0):
        calls.append(timeout)
        detail = json.dumps({"error": {"message": "bad key"}}).encode()
        raise urllib.error.HTTPError("http://ai", 401, "unauthorized", Message(), io.BytesIO(detail))

    monkeypatch.setattr(ai_mod.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(ai_mod.time, "sleep", lambda _s: pytest.fail("401 不该重试"))
    settings: Any = SimpleNamespace(ai_base="http://127.0.0.1:8317/v1", ai_model="m", ai_key="k")
    with pytest.raises(AiError) as caught:
        complete(settings, "提示词")
    assert caught.value.retryable is False
    assert caught.value.status == 401
    assert len(calls) == 1


@pytest.mark.parametrize("text,code", [
    ("WARNING 等待岗位详情超时\n", 2),
    ("INFO 筛选结果：人工停止\n", 2), ("INFO 筛选结果：熔断\n", 2),
    ("INFO 筛选结果：异常\n", 2), ("INFO 筛选结果：完成\n", 0),
])
def test_watch_requires_completion_proof(tmp_path, text, code):
    p = tmp_path / "screen.log"
    p.write_text(text)
    assert watch_log(p, lambda: False, out=io.StringIO()) == code


def test_resume_watch_replays_gap_alert_but_recognizes_later_recovery(tmp_path):
    p = tmp_path / "screen.log"
    p.write_text("INFO 流式筛选开始\nWARNING 暂停等人：接口异常\n")
    offset, found = _last_run(p)
    assert found
    assert watch_log(p, lambda: True, offset=offset, out=io.StringIO()) == 2
    with p.open("a") as f:
        f.write("INFO 目标业务已恢复，继续\nINFO 筛选结果：完成\n")
    assert watch_log(p, lambda: False, offset=offset, out=io.StringIO()) == 0


def test_log_truncation_does_not_hide_finish(tmp_path):
    p = tmp_path / "screen.log"
    p.write_text("INFO 筛选结果：完成\n")
    assert watch_log(p, lambda: False, offset=1000, out=io.StringIO()) == 0


def test_open_chrome_does_not_expose_remote_debugging_port(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    class FakeChromium:
        def launch_persistent_context(self, _user_data, **kwargs):
            captured.update(kwargs)
            return "ctx"

    class FakePlaywright:
        chromium = FakeChromium()

        def start(self):
            return self

    monkeypatch.setattr("patchright.sync_api.sync_playwright", lambda: FakePlaywright())
    open_chrome(tmp_path / "browser-data")
    assert all(not str(arg).startswith("--remote-debugging-port") for arg in captured["args"])


def test_watch_does_not_auto_restart_finished_run_without_start_flag(monkeypatch, tmp_path):
    log_file = tmp_path / "screen.log"
    log_file.write_text("INFO 流式筛选开始\nINFO 筛选结果：熔断\n", encoding="utf-8")
    monkeypatch.setattr(watch_mod, "load_settings", lambda: SimpleNamespace(log_file=log_file))
    monkeypatch.setattr(watch_mod, "running_pid", lambda *_args: None)
    monkeypatch.setattr(watch_mod, "_spawn_detached", lambda *_args: pytest.fail("must not auto-start new round"))
    assert watch_mod.main(start=False) == 2

