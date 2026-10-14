import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

from boss_screen import watch as watch_mod
from boss_screen.browser import open_chrome, risk_state
from boss_screen.cards import Card, ingest_job_list, parse_detail
from boss_screen.page_facts import PageFacts
from boss_screen.run import KeywordStats, Session, _landed
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


def test_network_failure_pauses_current_generation_only():
    facts = PageFacts(Page())
    request = SimpleNamespace(url=DETAIL)
    facts.on_request(request)
    facts.on_failed(request)
    assert facts.fault is not None
    assert facts.fault.kind == "detail"


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


def test_jd_failures_trip_circuit_while_browsing_and_in_pending_retry(session):
    session._screen_job = lambda _kw, _job: "ai_jd_pending"
    with ThreadPoolExecutor(1) as pool:
        for _ in range(3):
            session._submit_jd(pool, "Agent", {}).result()
    assert session.stop.is_set()
    assert session.end_reason == "熔断"


def test_pending_jd_retry_uses_same_circuit(session):
    session.store.pending_jd_rows = lambda: [{"keyword": "Agent"}] * 5
    session._screen_job = lambda _kw, _job: "ai_jd_pending"
    session._retry_pending_jds()
    assert session.stop.is_set()
    assert session.ai_fail_streak == 3


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

