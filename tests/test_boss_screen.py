import json
import logging
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import yaml

from boss_screen.ai import parse_jd, parse_title_action
from boss_screen.browser import detail_gap_seconds, halt_if_risk, proxy_args
from boss_screen.cards import Card, ingest_job_list, overlay, parse_detail
from boss_screen.config import load_settings, search_url, setup_logging
from boss_screen.proc_lock import acquire, release, take_lock
from boss_screen.rules import (
    classify_city,
    contains_job_token,
    detail_rule_drop_reason,
    is_active_within_3_days,
    next_step,
    rule_drop_reason,
    title_disposition,
)
from boss_screen.run import Session
from boss_screen.store import JobStore


def test_city_page_uses_city_name_only():
    assert classify_city("杭州·西湖区·西溪") == "杭州"
    assert classify_city("上海·浦东新区") == "上海"
    assert classify_city("余杭区") == "其它"
    assert classify_city("") == "其它"


def test_training_token_skips_post_training():
    assert contains_job_token("后训练实习生", "训练") is False
    assert contains_job_token("数据训练师", "训练") is True


def test_list_and_detail_rules():
    kwargs = {
        "black_jobs": [],
        "black_companies": [],
        "black_recruiters": [],
        "company_tokens": ["外包"],
        "job_tokens": ["运营", "前端"],
    }
    assert rule_drop_reason("AI Agent运营", "玩点", "", "", **kwargs) == "岗位名含：运营"
    assert rule_drop_reason("后端", "外包公司", "", "", **kwargs) == "公司名含：外包"
    assert rule_drop_reason("Agent", "华为", "猎头", "", **kwargs) == "招聘者含：猎头"
    assert rule_drop_reason("Agent", "华为", "技术负责人", "", **kwargs) is None

    assert detail_rule_drop_reason("本周活跃", "工程师", "", []) == "HR活跃度缺失或未近3天活跃：本周活跃"
    assert detail_rule_drop_reason("", "工程师", "", []) == "HR活跃度缺失或未近3天活跃：未知"
    assert detail_rule_drop_reason("true", "工程师", "", []) == "HR活跃度缺失或未近3天活跃：true"
    assert detail_rule_drop_reason("刚刚活跃", "猎头顾问", "", []) == "招聘者含：猎头"
    assert detail_rule_drop_reason("刚刚活跃", "工程师", "", []) is None
    assert is_active_within_3_days("") is False
    assert is_active_within_3_days("刚刚活跃") is True
    assert is_active_within_3_days("未知") is False


def test_blacklist_reason_uses_the_first_matching_term():
    kwargs = {
        "black_jobs": ["Agent", "开发"],
        "black_companies": ["甲", "公司"],
        "black_recruiters": ["李", "负责人"],
        "company_tokens": [],
        "job_tokens": [],
    }
    assert rule_drop_reason("Agent 开发", "乙", "", "", **kwargs) == "职位黑名单命中：Agent"
    assert rule_drop_reason("后端", "甲公司", "", "", **kwargs) == "公司黑名单命中：甲"
    assert rule_drop_reason("后端", "乙", "技术负责人", "李", **kwargs) == "招聘者黑名单命中：负责人"
    assert rule_drop_reason("后端", "乙", "工程师", "李", **kwargs) == "招聘者黑名单命中：李"


def test_title_disposition_separates_stage_from_clean_reason():
    stage, reason, click = title_disposition("click", "Agent 应用开发", "其它", 3)
    assert stage == "jd_queued"
    assert reason == "Agent 应用开发"
    assert click is False

    stage, reason, click = title_disposition("park", "职责看不准", "杭州", 3)
    assert stage == "jd_park"
    assert reason == "职责看不准"
    assert click is False

    stage, reason, click = title_disposition("click", "Agent 应用开发", "上海", 1)
    assert stage == "jd_queued"
    assert reason == "Agent 应用开发"
    assert click is True

    stage, reason, click = title_disposition("click", "Agent 应用开发", "杭州", 0)
    assert stage == "jd_queued"
    assert reason == "Agent 应用开发"
    assert click is False

    stage, reason, click = title_disposition("drop", "纯运营岗位", "杭州", 1)
    assert stage == "ai_title_drop"
    assert reason == "纯运营岗位"
    assert click is False


def test_ai_reply_returns_decision_and_reason_from_json():
    assert parse_title_action('{"action":"click","reason":"Agent 开发"}') == ("click", "Agent 开发")
    assert parse_jd('{"keep":false,"reason":"纯前端"}') == (False, "纯前端")
    assert parse_jd('{"keep":true,"reason":"做 Agent"}') == (True, "做 Agent")


def test_ai_reply_does_not_guess_a_decision_outside_the_json_contract():
    assert parse_title_action('```json\n{"action":"click"}\n```')[0] is None
    assert parse_jd('{"keep":"invalid","extra":{"keep":true}}')[0] is None
    assert parse_jd("不是 json")[0] is None


def test_search_url_and_db_path(tmp_path: Path):
    path = tmp_path / "boss.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "keywords": ["AI Agent"],
                "cities": ["杭州"],
                "jobType": "实习",
                "experience": ["在校生", "应届毕业生"],
                "degree": ["本科"],
                "industry": [],
                "salary": [],
                "scale": [],
                "stage": [],
                "waitTime": 3,
                "keywordGapSeconds": 60,
                "detailLimit": 0,
                "onRisk": "stop",
                "dbPath": "screen-results/boss.db",
                "ai": {"baseUrl": "http://127.0.0.1:8317/v1", "apiKey": "k", "model": "m"},
                "rules": {"companyTokens": [], "jobTitleTokens": ["运营"]},
                "blacklist": {"companies": [], "jobs": [], "recruiters": []},
                "candidateProfile": "材料",
                "prompts": {"title": "标题 {job}", "jd": "JD {jd}"},
                "codes": {
                    "city": {"杭州": "101210100"},
                    "jobType": {"实习": "1902"},
                    "experience": {"在校生": "108", "应届毕业生": "102"},
                    "degree": {"本科": "203"},
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.wait_time == 18
    assert settings.browser_data == tmp_path / "browser-data"
    assert settings.db_path == tmp_path / "screen-results" / "boss.db"
    assert settings.log_file == tmp_path / "screen-results" / "screen.log"
    url = search_url(settings, "101210100")
    assert url.startswith("https://www.zhipin.com/web/geek/jobs?")
    assert "city=101210100" in url
    assert "jobType=1902" in url
    assert "experience=108,102" in url
    assert "degree=203" in url
    assert "industry=" not in url


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("keywords", "AI Agent", "名单须用列表"), ("cities", ["101210100"], "无法对应 Boss 选项")],
)
def test_config_requires_lists_and_named_options(tmp_path: Path, field: str, value, message: str):
    data = {
        "keywords": ["AI Agent"],
        "cities": ["杭州"],
        "ai": {"baseUrl": "http://127.0.0.1/v1", "apiKey": "k", "model": "m"},
        "prompts": {"title": "t", "jd": "j"},
        "codes": {"city": {"杭州": "101210100"}},
    }
    data[field] = value
    path = tmp_path / "boss.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(SystemExit, match=message):
        load_settings(path)


def test_sqlite_store_upserts_merges_fields_and_collects_keywords(tmp_path: Path):
    db_path = tmp_path / "screen-results" / "boss.db"
    store = JobStore(db_path)
    try:
        store.upsert(
            {
                "encryptId": "abc_1",
                "keyword": "AI Agent",
                "company": "甲科技",
                "job": "Agent 开发实习生",
                "salary": "200-300/天",
                "area": "杭州·西湖区",
                "cityPage": "杭州",
                "tags": "Python、RAG",
                "degree": "本科",
                "experience": "在校生",
                "industry": "人工智能",
                "scale": "100-499人",
                "financing": "B轮",
                "stage": "jd_queued",
                "reason": "标题契合",
            }
        )
        # 模拟点开详情后补全 JD 与 HR 活跃度，原有列表字段不丢失
        store.upsert(
            {
                "encryptId": "abc_1",
                "keyword": "大模型应用",
                "active": "刚刚活跃",
                "jd": "负责 Agent 工具调用与评测体系",
                "stage": "ai_keep",
                "reason": "【职责与技术】做 Agent。【对标与切入】retail-bench。【公司背景】人工智能。【排雷风险】无明显硬伤。",
            }
        )
    finally:
        store.close()

    reopened = JobStore(db_path)
    try:
        row = reopened.get("abc_1")
        assert row is not None
        assert row["stage"] == "ai_keep"
        assert row["jd"] == "负责 Agent 工具调用与评测体系"
        assert row["salary"] == "200-300/天"
        assert row["tags"] == "Python、RAG"
        assert row["degree"] == "本科"
        assert row["industry"] == "人工智能"
        assert row["keywords"] == ["AI Agent", "大模型应用"]
        assert row["firstSeenAt"] <= row["updatedAt"]
    finally:
        reopened.close()


def test_sqlite_store_returns_pending_jd_rows_with_captured_jd(tmp_path: Path):
    store = JobStore(tmp_path / "boss.db")
    try:
        store.upsert(
            {
                "encryptId": "has_jd",
                "company": "甲",
                "job": "开发",
                "cityPage": "杭州",
                "jd": "正文内容",
                "stage": "ai_jd_pending",
                "reason": "JD请求失败",
            }
        )
        store.upsert(
            {
                "encryptId": "no_jd",
                "company": "乙",
                "job": "开发",
                "cityPage": "杭州",
                "jd": "",
                "stage": "ai_jd_pending",
                "reason": "JD请求失败",
            }
        )
        store.upsert(
            {
                "encryptId": "queued_with_jd",
                "company": "丙",
                "job": "开发",
                "cityPage": "杭州",
                "jd": "已抓取但中断的JD",
                "stage": "jd_queued",
                "reason": "标题契合",
            }
        )
        pending = store.pending_jd_rows()
        assert [r["encryptId"] for r in pending] == ["has_jd", "queued_with_jd"]
    finally:
        store.close()


def test_revisit_skips_all_terminal_stages_and_advances_queued_jobs():
    for terminal in ("ai_keep", "rule_drop", "ai_title_drop", "ai_jd_drop"):
        assert next_step({"stage": terminal, "cityPage": "杭州"}, "杭州", "岗位名含：运营", 3) == "skip"

    assert next_step(None, "杭州", "岗位名含：运营", 3) == "rule"
    assert next_step(None, "杭州", None, 3) == "title"

    queued = {"stage": "jd_queued", "cityPage": "杭州"}
    assert next_step(queued, "杭州", None, 2) == "click"
    assert next_step(queued, "杭州", None, 0) == "leave"
    assert next_step(queued, "其它", None, 2) == "leave"
    assert next_step({"stage": "jd_queued", "cityPage": "杭州", "jd": "已抓到正文"}, "杭州", None, 2) == "jd"

    parked = {"stage": "jd_park", "cityPage": "杭州"}
    assert next_step(parked, "杭州", None, 3) == "leave"

    assert next_step({"stage": "ai_title_pending", "cityPage": "杭州"}, "杭州", None, 3) == "title"
    assert next_step({"stage": "ai_jd_pending", "cityPage": "杭州", "jd": "做工具"}, "杭州", None, 0) == "jd"
    assert next_step({"stage": "ai_jd_pending", "cityPage": "杭州", "jd": ""}, "杭州", None, 1) == "click"
    assert next_step({"stage": "ai_jd_pending", "cityPage": "杭州", "jd": ""}, "杭州", None, 0) == "leave"


def test_list_json_and_detail_fields():
    body = json.dumps(
        {
            "zpData": {
                "jobList": [
                    {
                        "encryptJobId": "abc_1",
                        "jobName": "Agent 开发",
                        "salaryDesc": "250-300元/天",
                        "brandName": "甲",
                        "brandIndustry": "人工智能",
                        "brandScaleName": "100-499人",
                        "brandStageName": "B轮",
                        "jobDegree": "本科",
                        "jobExperience": "在校/应届",
                        "cityName": "杭州",
                        "areaDistrict": "西湖区",
                        "businessDistrict": "西溪",
                        "skills": ["Python", "RAG"],
                        "bossName": "王先生",
                        "bossTitle": "技术负责人",
                    }
                ]
            }
        }
    )
    cards = ingest_job_list(body)
    assert len(cards) == 1
    c = cards[0]
    assert c.encrypt_id == "abc_1"
    assert c.area == "杭州·西湖区·西溪"
    assert c.salary == "250-300元/天"
    assert c.tags == "Python、RAG"
    assert c.recruiter == "王先生"
    assert c.recruiter_title == "技术负责人"
    assert c.degree == "本科"
    assert c.experience == "在校/应届"
    assert c.industry == "人工智能"
    assert c.scale == "100-499人"
    assert c.financing == "B轮"

    merged = overlay(Card(encrypt_id="abc_1", job="Agent 开发", company="甲", area="杭州"), c)
    assert merged.salary == "250-300元/天"
    assert merged.tags == "Python、RAG"

    detail = parse_detail(
        json.dumps(
            {
                "zpData": {
                    "jobInfo": {
                        "jobName": "Agent 开发",
                        "postDescription": "做工具",
                        "locationName": "杭州",
                        "salaryDesc": "200-300/天",
                        "degreeName": "本科",
                        "experienceName": "在校生",
                    },
                    "bossInfo": {"name": "李", "title": "猎头", "activeTimeDesc": "本月活跃"},
                    "brandComInfo": {"brandName": "甲", "industryName": "人工智能", "scaleName": "100-499人"},
                }
            }
        )
    )
    assert detail["company"] == "甲"
    assert detail["financing"] == ""
    assert detail["active"] == "本月活跃"
    assert detail["jd"] == "做工具"


def test_detail_gap_stays_within_half_and_full():
    random.seed(1)
    for _ in range(30):
        gap = detail_gap_seconds(18)
        assert 9 <= gap <= 18


def test_chrome_proxy_follows_environment():
    assert proxy_args({"https_proxy": "http://127.0.0.1:7897"}) == [
        "--proxy-server=http://127.0.0.1:7897",
        "--proxy-bypass-list=localhost;127.0.0.1;::1",
    ]
    assert proxy_args({"http_proxy": "http://127.0.0.1:7897"})[0] == "--proxy-server=http://127.0.0.1:7897"
    assert proxy_args({}) == []


def test_second_process_cannot_take_the_lock(tmp_path: Path):
    held = tmp_path / "run.lock"
    src = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import sys, time\n"
        "from pathlib import Path\n"
        "from boss_screen.proc_lock import acquire\n"
        "lock = acquire(Path(sys.argv[1]))\n"
        "assert lock is not None\n"
        "print('HELD', flush=True)\n"
        "time.sleep(30)\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src)
    proc = subprocess.Popen(
        [sys.executable, "-c", code, str(held)],
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        line = proc.stdout.readline() if proc.stdout else ""
        assert line.startswith("HELD")
        assert acquire(held) is None
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    again = None
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        again = acquire(held)
        if again is not None:
            break
        time.sleep(0.05)
    assert again is not None
    release(again)


def test_take_lock_refuses_when_held(tmp_path: Path):
    lock_file = tmp_path / "run.lock"
    held = acquire(lock_file)
    try:
        assert lock_file.read_text(encoding="ascii").strip() == str(os.getpid())
        with pytest.raises(SystemExit) as caught:
            take_lock(lock_file)
        assert caught.value.code == 1
        assert lock_file.read_text(encoding="ascii").strip() == str(os.getpid())
    finally:
        release(held)


def test_url_read_failure_does_not_count_as_verification_gone():
    page = _UrlPage(
        [
            "https://www.zhipin.com/web/user/safe/verify-slider",
            RuntimeError("closed"),
            "https://www.zhipin.com/web/geek/job",
        ]
    )
    stop = threading.Event()
    assert halt_if_risk(page, stop, False, "筛选", poll_seconds=0) is False
    assert page.urls == []
    assert not stop.is_set()


def test_url_read_failure_stops_when_on_risk_is_stop():
    page = _UrlPage([RuntimeError("closed")])
    stop = threading.Event()
    assert halt_if_risk(page, stop, True, "筛选", poll_seconds=0) is True
    assert stop.is_set()


def test_setup_logging_writes_to_file(tmp_path: Path):
    target = tmp_path / "custom.log"
    setup_logging(target)
    test_log = logging.getLogger("boss_screen")
    test_log.info("测试写入运行日志")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = target.read_text(encoding="utf-8")
    assert "测试写入运行日志" in content

    setup_logging(None)
    assert not any(isinstance(handler, logging.FileHandler) for handler in logging.getLogger().handlers)


def test_load_settings_log_file_options(tmp_path: Path):
    base_data = {
        "keywords": ["AI Agent"],
        "cities": ["杭州"],
        "ai": {"baseUrl": "http://127.0.0.1/v1", "apiKey": "k", "model": "m"},
        "prompts": {"title": "t", "jd": "j"},
        "codes": {"city": {"杭州": "101210100"}},
    }
    p1 = tmp_path / "b1.yaml"
    p1.write_text(yaml.safe_dump({**base_data, "logFile": "logs/test.log"}), encoding="utf-8")
    s1 = load_settings(p1)
    assert s1.log_file == tmp_path / "logs" / "test.log"

    p2 = tmp_path / "b2.yaml"
    p2.write_text(yaml.safe_dump({**base_data, "logFile": ""}), encoding="utf-8")
    s2 = load_settings(p2)
    assert s2.log_file is None


def test_detail_attempts_only_increment_after_click():
    session: Any = Session.__new__(Session)
    session.detail_attempts = 0
    session.settings = type("Settings", (), {"detail_limit": 1})()
    session.stop = threading.Event()
    session.page = _DetailPage()
    session._halt = lambda _reason: False
    session._card_locator = lambda _encrypt_id: _DetailTarget()
    click_count = 0

    def click(_target):
        nonlocal click_count
        click_count += 1

    session._human_click = click
    session._job_from_detail = lambda _card, _body: None
    session._pause_between_jobs = lambda: None

    pool: Any = _ImmediatePool()
    session._click_details("AI Agent", [Card(encrypt_id="one", job="开发", company="甲")], pool, [])

    assert session.detail_attempts == 1
    assert click_count == 1


def test_missing_detail_card_does_not_consume_detail_limit():
    session: Any = Session.__new__(Session)
    session.detail_attempts = 0
    session.settings = type("Settings", (), {"detail_limit": 1})()
    session.stop = threading.Event()
    session.page = _DetailPage()
    session._halt = lambda _reason: False
    targets = iter([None, _DetailTarget()])
    session._card_locator = lambda _encrypt_id: next(targets)
    session._human_click = lambda _target: None
    session._job_from_detail = lambda _card, _body: None
    session._pause_between_jobs = lambda: None

    pool: Any = _ImmediatePool()
    cards = [Card(encrypt_id="one", job="开发", company="甲"), Card(encrypt_id="two", job="开发", company="乙")]
    session._click_details("AI Agent", cards, pool, [])

    assert session.detail_attempts == 1


def test_detail_timeout_does_not_retry_the_same_click():
    session: Any = Session.__new__(Session)
    session.detail_attempts = 0
    session.settings = type("Settings", (), {"detail_limit": 1})()
    session.stop = threading.Event()
    session.page = _TimeoutDetailPage()
    session._halt = lambda _reason: False
    session._card_locator = lambda _encrypt_id: _DetailTarget()
    click_count = 0

    def click(_target):
        nonlocal click_count
        click_count += 1

    session._human_click = click
    session._job_from_detail = lambda _card, _body: None
    session._pause_between_jobs = lambda: None

    pool: Any = _ImmediatePool()
    session._click_details("AI Agent", [Card(encrypt_id="one", job="开发", company="甲")], pool, [])

    assert session.detail_attempts == 1
    assert click_count == 1

def test_detail_response_is_stored_before_stop_signal():
    session: Any = Session.__new__(Session)
    session.detail_attempts = 0
    session.settings = type("Settings", (), {"detail_limit": 1, "black_recruiters": []})()
    session.stop = threading.Event()
    session.page = _DetailPage()
    session._halt = lambda _reason: False
    session._card_locator = lambda _encrypt_id: _DetailTarget()
    session._human_click = lambda _target: None
    stored: list[dict] = []
    session.store = type("Store", (), {"upsert": lambda _self, row: stored.append(row) or row})()
    session._job_from_detail = lambda card, _body: session.stop.set() or {
        "encryptId": card.encrypt_id,
        "company": card.company,
        "job": card.job,
        "active": "刚刚活跃",
        "recruiter": "王",
        "recruiterTitle": "工程师",
        "jd": "岗位正文",
    }
    session._pause_between_jobs = lambda: None

    pool: Any = _ImmediatePool()
    session._click_details("AI Agent", [Card(encrypt_id="one", job="开发", company="甲")], pool, [])

    assert stored == [
        {
            "encryptId": "one",
            "company": "甲",
            "job": "开发",
            "active": "刚刚活跃",
            "recruiter": "王",
            "recruiterTitle": "工程师",
            "jd": "岗位正文",
            "keyword": "AI Agent",
        }
    ]


def test_detail_failures_pause_abort_keyword_on_two_strikes_and_stop_run_on_third():
    session: Any = Session.__new__(Session)
    session.detail_attempts = 0
    session.detail_fail_streak = 0
    session.keyword_aborted = False
    session.settings = type("Settings", (), {"detail_limit": -1})()
    session.stop = threading.Event()
    session.page = _TimeoutDetailPage()
    session._halt = lambda _reason: False
    session._card_locator = lambda _encrypt_id: _DetailTarget()
    session._human_click = lambda _target: None
    pauses = 0

    def record_pause():
        nonlocal pauses
        pauses += 1

    session._pause_between_jobs = record_pause

    pool: Any = _ImmediatePool()
    cards = [
        Card(encrypt_id="one", job="开发1", company="甲"),
        Card(encrypt_id="two", job="开发2", company="乙"),
        Card(encrypt_id="three", job="开发3", company="丙"),
    ]
    session._click_details("AI Agent", cards, pool, [])

    # 第 1 次失败后执行了停顿；第 2 次失败触发关键词级熔断，第 3 张卡片不再点击
    assert session.detail_attempts == 2
    assert pauses == 1
    assert session.keyword_aborted is True
    assert not session.stop.is_set()

    # 下一个关键词重置 keyword_aborted，但若刷新页面后首击仍失败（第 3 次连续失败），直接停机保护账号
    session.keyword_aborted = False
    session._click_details("大模型", [Card(encrypt_id="four", job="开发4", company="丁")], pool, [])
    assert session.detail_attempts == 3
    assert session.stop.is_set()


def test_same_run_skips_reclicking_already_attempted_encrypt_id():
    session: Any = Session.__new__(Session)
    session.detail_attempts = 0
    session.detail_fail_streak = 0
    session.keyword_aborted = False
    session.attempted_details = {"dup_1"}
    session.settings = type("Settings", (), {"detail_limit": -1})()
    session.stop = threading.Event()
    session.page = _DetailPage()
    session._halt = lambda _reason: False
    session._card_locator = lambda _encrypt_id: _DetailTarget()
    session._human_click = lambda _target: None
    session._job_from_detail = lambda _card, _body: None
    session._pause_between_jobs = lambda: None

    pool: Any = _ImmediatePool()
    session._click_details("大模型", [Card(encrypt_id="dup_1", job="开发", company="甲")], pool, [])
    assert session.detail_attempts == 0


def test_stream_list_emits_keyword_summary_log(caplog: pytest.LogCaptureFixture):
    session: Any = Session.__new__(Session)
    session.stop = threading.Event()
    session.keyword_aborted = False
    session._halt = lambda _reason: False
    session._harvest_new = lambda handled: (
        handled.update({"a", "b"}) or [Card(encrypt_id="a", job="开发", company="甲"), Card(encrypt_id="b", job="运营", company="乙")]
        if not handled
        else []
    )

    def fake_process(_keyword, _batch, consecutive_seen, _jd_pool, _jd_futures, stats):
        stats.skipped = 1
        stats.rule_drops = 1
        return consecutive_seen

    session._process_batch = fake_process
    session._footer_visible = lambda: True
    session._scroll_step = lambda: True

    with caplog.at_level(logging.INFO, logger="boss_screen"):
        session._stream_list("AI Agent")

    assert any("【AI Agent】汇总：卡片 2（终局跳过 1）| 规则淘汰 1" in rec.message for rec in caplog.records)


class _ImmediatePool:
    def submit(self, *_args, **_kwargs):
        raise AssertionError("详情为空时不应提交 JD AI")


class _DetailTarget:
    def click(self):
        return None


class _DetailResponse:
    def text(self):
        return "{}"


class _DetailWait:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    @property
    def value(self):
        return _DetailResponse()


class _DetailPage:
    def expect_response(self, _predicate, timeout: int):
        assert timeout == 15_000
        return _DetailWait()


class _TimeoutDetailWait:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        raise TimeoutError("detail response timeout")


class _TimeoutDetailPage:
    def expect_response(self, _predicate, timeout: int):
        assert timeout == 15_000
        return _TimeoutDetailWait()


class _UrlPage:
    def __init__(self, urls: list[object]) -> None:
        self.urls = list(urls)

    @property
    def url(self):
        item = self.urls.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def locator(self, _selector: str):
        return _NoWidgets()


class _NoWidgets:
    def count(self) -> int:
        return 0
