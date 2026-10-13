import json
import logging
import os
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

from boss_screen.ai import parse_keep, parse_title_action
from boss_screen.browser import detail_gap_seconds, halt_if_risk, proxy_args
from boss_screen.cards import ingest_job_list, parse_detail
from boss_screen.chat import (
    _parse_args,
    button_action,
    first_visible_action,
    next_chat_step,
    should_record,
)
from boss_screen.config import Settings, load_settings, screen_file_name, search_url, setup_logging
from boss_screen.opened import append_opened, load_ids
from boss_screen.proc_lock import acquire, release, take_lock
from boss_screen.rules import (
    classify_city,
    contains_job_token,
    is_active_within_3_days,
    jd_retry_city,
    next_step,
    rule_drop_reason,
    saved_jd_job,
    title_disposition,
)
from boss_screen.store import ScreenLog, load_seen


def test_city_page_uses_city_name_only():
    assert classify_city("杭州·西湖区·西溪") == "杭州"
    assert classify_city("上海·浦东新区") == "上海"
    assert classify_city("余杭区") == "其它"
    assert classify_city("") == "其它"


def test_training_token_skips_post_training():
    assert contains_job_token("后训练实习生", "训练") is False
    assert contains_job_token("数据训练师", "训练") is True


def test_list_rule_drops_job_token_and_inactive_hr():
    kwargs = {
        "black_jobs": [],
        "black_companies": [],
        "black_recruiters": [],
        "company_tokens": ["外包"],
        "job_tokens": ["运营", "前端"],
    }
    assert rule_drop_reason("AI Agent运营", "玩点", "", "", "", **kwargs) == "岗位名含：运营"
    assert rule_drop_reason("后端", "外包公司", "", "", "", **kwargs) == "公司名含：外包"
    assert rule_drop_reason("Agent", "华为", "本周活跃", "工程师", "", **kwargs) == "HR未近3天活跃：本周活跃"
    assert rule_drop_reason("Agent", "华为", "", "猎头", "", **kwargs) == "招聘者含：猎头"
    assert rule_drop_reason("Agent", "华为", "刚刚活跃", "", "", **kwargs) is None
    assert is_active_within_3_days("") is False


def test_title_disposition_parks_other_city_and_caps_clicks():
    stage, reason, click = title_disposition("click", "可点", "其它", 3)
    assert stage == "jd_wait_other"
    assert "本轮不点详情" in reason
    assert click is False

    stage, reason, click = title_disposition("park", "看不准", "杭州", 3)
    assert stage == "jd_wait"
    assert "将点详情" not in reason
    assert click is False

    stage, reason, click = title_disposition("click", "可点", "上海", 1)
    assert stage == "jd_wait" and click is True and "将点详情" in reason

    stage, reason, click = title_disposition("click", "可点", "杭州", 0)
    assert click is False and "详情上限" in reason

    stage, reason, _click = title_disposition("drop", "运营", "杭州", 1)
    assert stage == "ai_title_drop" and reason.startswith("规则") is False
    assert reason.startswith("AI 标题")


def test_ai_parsers_accept_fenced_json():
    raw = '```json\n{"action":"click","reason":"Agent 开发"}\n```'
    assert parse_title_action(raw) == ("click", "Agent 开发")
    assert parse_keep('说明 {"keep": false, "reason": "纯前端"}') is False
    assert parse_keep("不是 json") is None


def test_search_url_and_file_name(tmp_path: Path):
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
                "screenResultsDir": "screen-results",
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
    assert settings.opened_chats == tmp_path / "opened-chats.jsonl"
    assert settings.resume_image == tmp_path / "resume.jpg"
    assert settings.screen_dir == tmp_path / "screen-results"
    assert settings.log_file == tmp_path / "screen-results" / "screen.log"
    url = search_url(settings, "101210100")
    assert url.startswith("https://www.zhipin.com/web/geek/jobs?")
    assert "city=101210100" in url
    assert "jobType=1902" in url
    assert "experience=108,102" in url
    assert "degree=203" in url
    assert "industry=" not in url
    assert screen_file_name("20260922-010102", "实习", "AI Agent") == "20260922-010102_实习_AI-Agent.jsonl"


def test_jsonl_keeps_history_and_merges_keywords(tmp_path: Path):
    path = tmp_path / "one.jsonl"
    screen = ScreenLog(path)
    screen.upsert(
        {
            "keyword": "AI Agent",
            "company": "甲",
            "job": "开发",
            "encryptId": "abc",
            "cityPage": "杭州",
            "stage": "ai_keep",
            "reason": "AI JD 保留",
            "active": "本周活跃",
            "hrDrop": False,
            "hasJd": True,
            "keep": True,
        }
    )
    original = path.read_text(encoding="utf-8")
    again = ScreenLog(path)
    again.load()
    row = again.rows["id:abc"]
    assert "keep" not in row
    assert row["stage"] == "ai_keep"
    assert path.read_text(encoding="utf-8") == original

    screen.upsert(
        {
            "keyword": "Agent开发",
            "company": "乙",
            "job": "运营",
            "encryptId": "def",
            "cityPage": "上海",
            "stage": "rule_drop",
            "reason": "规则 岗位名含：运营",
            "hrDrop": False,
            "hasJd": False,
        }
    )
    loaded = ScreenLog(path)
    loaded.load()
    assert loaded.rows["id:def"]["keywords"] == ["Agent开发"]
    assert loaded.rows["id:abc"]["keywords"] == ["AI Agent"]


def test_seen_index_prefers_newer_stamp_then_later_keyword(tmp_path: Path):
    older = tmp_path / "20260921-010101_实习_AI-Agent.jsonl"
    newer_first = tmp_path / "20260922-010101_实习_AI-Agent.jsonl"
    newer_second = tmp_path / "20260922-010101_实习_Agent开发.jsonl"
    row = {
        "company": "甲",
        "job": "开发",
        "encryptId": "abc",
        "cityPage": "杭州",
        "hrDrop": False,
        "hasJd": False,
    }
    older.write_text(_line({**row, "stage": "ai_title_drop", "reason": "AI 标题 旧"}), encoding="utf-8")
    newer_first.write_text(_line({**row, "stage": "jd_wait", "reason": "AI 标题 可点；将点详情"}), encoding="utf-8")
    newer_second.write_text(_line({**row, "stage": "ai_keep", "reason": "AI JD 保留"}), encoding="utf-8")
    before = newer_first.read_text(encoding="utf-8")
    seen = load_seen(tmp_path, ["AI Agent", "Agent开发"])
    assert seen["id:abc"]["stage"] == "ai_keep"
    assert newer_first.read_text(encoding="utf-8") == before


def test_seen_index_same_stamp_follows_write_time_when_keyword_left_the_list(tmp_path: Path):
    early = tmp_path / "20260921-150408_实习_智能体应用.jsonl"
    late = tmp_path / "20260921-150408_实习_AI应用开发.jsonl"
    row = {
        "company": "甲",
        "job": "开发",
        "encryptId": "abc",
        "cityPage": "杭州",
        "hrDrop": False,
        "hasJd": False,
    }
    early.write_text(_line({**row, "stage": "jd_wait", "reason": "AI 标题 可点；将点详情"}), encoding="utf-8")
    late.write_text(_line({**row, "stage": "ai_title_drop", "reason": "AI 标题 偏了"}), encoding="utf-8")
    os.utime(early, ns=(1_000_000_000, 1_000_000_000))
    os.utime(late, ns=(2_000_000_000, 2_000_000_000))
    seen = load_seen(tmp_path, ["AI Agent", "Agent开发"])
    assert seen["id:abc"]["stage"] == "ai_title_drop"


def test_revisit_skips_terminal_clicks_pending_and_retries_saved_jd():
    assert next_step({"stage": "ai_keep", "cityPage": "杭州", "active": "刚刚活跃"}, "杭州", None, 3) == "skip"
    assert next_step({"stage": "rule_drop", "cityPage": "杭州", "hrDrop": True, "active": "本月活跃"}, "杭州", "岗位名含：运营", 3) == "skip"
    assert next_step({"stage": "ai_keep", "cityPage": "杭州", "active": "本周活跃"}, "杭州", None, 3) == "reclass"
    assert next_step({"stage": "ai_title_drop", "cityPage": "杭州", "active": "本周活跃"}, "杭州", None, 3) == "skip"
    assert next_step({"stage": "ai_jd_drop", "cityPage": "杭州", "active": "本月活跃"}, "杭州", None, 3) == "skip"
    stale_pending = {"stage": "jd_wait", "cityPage": "杭州", "reason": "AI 标题 可点；将点详情", "active": "本周活跃"}
    assert next_step(stale_pending, "杭州", None, 2) == "click"
    stale_title = {"stage": "ai_title_pending", "cityPage": "杭州", "active": "本周活跃"}
    assert next_step(stale_title, "杭州", None, 3) == "title"
    stale_jd = {"stage": "ai_jd_pending", "cityPage": "杭州", "jd": "做工具", "active": "本月活跃"}
    assert next_step(stale_jd, "杭州", None, 0) == "jd"
    assert next_step(None, "杭州", "岗位名含：运营", 3) == "rule"
    assert next_step(None, "杭州", None, 3) == "title"
    pending = {"stage": "jd_wait", "cityPage": "杭州", "reason": "AI 标题 可点；本轮详情上限"}
    assert next_step(pending, "杭州", None, 2) == "click"
    assert next_step(pending, "杭州", None, 0) == "leave"
    vague = {"stage": "jd_wait", "cityPage": "杭州", "reason": "AI 标题 看不准"}
    assert next_step(vague, "杭州", None, 3) == "leave"
    assert next_step({"stage": "ai_title_pending", "cityPage": "杭州"}, "杭州", None, 3) == "title"
    assert next_step({"stage": "ai_jd_pending", "cityPage": "杭州", "jd": "做工具"}, "杭州", None, 0) == "jd"
    assert next_step({"stage": "ai_jd_pending", "cityPage": "杭州", "jd": ""}, "杭州", None, 1) == "click"
    assert next_step({"stage": "ai_jd_pending", "cityPage": "杭州", "jd": ""}, "杭州", None, 0) == "leave"
    other = {"stage": "jd_wait_other", "cityPage": "其它", "reason": "AI 标题 可点；工作地「其它」，本轮不点详情"}
    assert next_step(other, "其它", None, 3) == "leave"
    assert next_step(other, "上海", None, 3) == "title"


def test_saved_jd_retry_omits_fields_that_are_not_stored():
    job = saved_jd_job(
        {
            "job": "开发",
            "company": "甲",
            "area": "杭州",
            "jd": "做工具",
            "active": "刚刚活跃",
            "recruiterTitle": "猎头",
            "degree": "本科",
            "salary": "200-300/天",
        },
        job="开发实习生",
        company="",
        area="",
        href="/job_detail/abc.html",
        encrypt_id="abc",
    )
    assert job["job"] == "开发实习生"
    assert job["company"] == "甲"
    assert job["jd"] == "做工具"
    assert job["salary"] == "200-300/天"
    assert job["degree"] == ""
    assert job["experience"] == ""
    assert job["industry"] == ""
    assert job["scale"] == ""
    assert job["financing"] == ""
    assert job["recruiterTitle"] == ""
    stored_area = saved_jd_job(
        {"company": "甲", "job": "开发", "area": "上海·浦东新区", "jd": "做工具"},
        job="开发",
        company="甲",
        area="",
        href="",
        encrypt_id="abc",
    )
    assert jd_retry_city(stored_area) == "上海"


def _line(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False) + "\n"


def test_list_json_and_detail_fields():
    body = json.dumps(
        {
            "zpData": {
                "jobList": [
                    {
                        "encryptId": "abc_1",
                        "jobName": "Agent 开发",
                        "brandName": "甲",
                        "cityName": "杭州",
                        "areaDistrict": "西湖区",
                        "businessDistrict": "西溪",
                        "activeTimeDesc": "刚刚活跃",
                        "skills": ["Python", "RAG"],
                        "bossTitle": "技术负责人",
                    }
                ]
            }
        }
    )
    cards = ingest_job_list(body)
    assert len(cards) == 1
    assert cards[0].area == "杭州·西湖区·西溪"
    assert cards[0].tags == "Python、RAG"
    assert cards[0].active == "刚刚活跃"
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


def test_continue_chat_does_not_send_again():
    assert button_action("继续沟通") == "opened"
    assert button_action(" 立即沟通 ") == "send"
    assert button_action("已沟通") == "absent"
    ids, image = _parse_args(["abc", "--image", "def"])
    assert ids == ["abc", "def"]
    assert image is True


def test_opened_chats_round_trip(tmp_path: Path):
    path = tmp_path / "opened-chats.jsonl"
    path.write_text("plain-id\n", encoding="utf-8")
    append_opened(path, "json-id", "甲", "开发")
    found = load_ids(path)
    assert found == {"plain-id", "json-id"}


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


def test_hidden_continue_button_is_not_opened():
    assert first_visible_action([("继续沟通", False), ("立即沟通", True)]) == ("send", 1)
    assert first_visible_action([("继续沟通", False)]) == ("absent", None)
    assert first_visible_action([(" 继续沟通 ", True)]) == ("opened", 0)


def test_leading_hyphen_encrypt_id_goes_after_options():
    assert _parse_args(["--image", "--", "-abc_1"]) == (["-abc_1"], True)
    with pytest.raises(SystemExit):
        _parse_args(["-abc_1"])


def test_take_lock_refuses_when_held(tmp_path: Path):
    held = acquire(tmp_path / "run.lock")
    try:
        with pytest.raises(SystemExit) as caught:
            take_lock(tmp_path / "run.lock")
        assert caught.value.code == 1
    finally:
        release(held)


def test_already_opened_does_not_open_detail():
    assert next_chat_step("abc", {"abc"}) == "skip"
    assert next_chat_step("abc", set()) == "open"
    assert next_chat_step("bad id", set()) == "invalid"


def test_failed_greeting_is_not_recorded_and_image_failure_keeps_the_record():
    assert should_record("send", False) is False
    assert should_record("absent", False) is False
    assert should_record("opened", False) is True
    assert should_record("send", True) is True


def test_send_img_resume_is_not_a_chat_setting(tmp_path: Path):
    path = tmp_path / "boss.yaml"
    path.write_text("sendImgResume: true\nscreenResultsDir: screen-results\n", encoding="utf-8")
    try:
        load_settings(path)
    except SystemExit:
        pass
    assert "send_img_resume" not in Settings.__dataclass_fields__
    assert _parse_args(["abc"]) == (["abc"], False)


def test_load_seen_ignores_another_directory(tmp_path: Path):
    seen = tmp_path / "screen-results"
    archive = tmp_path / "screen-experiments"
    seen.mkdir()
    archive.mkdir()
    row = {
        "company": "甲",
        "job": "开发",
        "stage": "ai_keep",
        "cityPage": "杭州",
        "reason": "AI JD 保留",
    }
    (seen / "20260922-010101_实习_A.jsonl").write_text(
        json.dumps({**row, "encryptId": "seen-id"}) + "\n",
        encoding="utf-8",
    )
    (archive / "20260922-020202_实习_A.jsonl").write_text(
        json.dumps({**row, "encryptId": "arch-id", "stage": "ai_title_drop"}) + "\n",
        encoding="utf-8",
    )
    loaded = load_seen(seen, ["A"])
    assert set(loaded) == {"id:seen-id"}


def test_url_read_failure_does_not_count_as_verification_gone():
    page = _UrlPage(
        [
            "https://www.zhipin.com/web/user/safe/verify-slider",
            RuntimeError("closed"),
            "https://www.zhipin.com/web/geek/job",
        ]
    )
    stop = threading.Event()
    assert halt_if_risk(page, stop, False, "代聊", poll_seconds=0) is False
    assert page.urls == []
    assert not stop.is_set()


def test_url_read_failure_stops_when_on_risk_is_stop():
    page = _UrlPage([RuntimeError("closed")])
    stop = threading.Event()
    assert halt_if_risk(page, stop, True, "代聊", poll_seconds=0) is True
    assert stop.is_set()


def test_screen_page_does_not_call_the_old_api():
    text = (Path(__file__).resolve().parents[1] / "screen" / "src" / "screen-board.tsx").read_text(
        encoding="utf-8"
    )
    assert "9527" not in text
    assert "ack-human" not in text


def test_setup_logging_writes_to_file(tmp_path: Path):
    target = tmp_path / "custom.log"
    log_file = setup_logging(target)
    assert log_file == target
    assert log_file is not None
    test_log = logging.getLogger("boss_screen")
    test_log.info("测试写入运行日志")
    for handler in logging.getLogger().handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "测试写入运行日志" in content

    # 当 log_file 为 None 时只打控制台，不报错
    assert setup_logging(None) is None


def test_load_settings_log_file_options(tmp_path: Path):
    base_data = {
        "keywords": ["AI Agent"],
        "cities": ["杭州"],
        "ai": {"baseUrl": "http://127.0.0.1/v1", "apiKey": "k", "model": "m"},
        "prompts": {"title": "t", "jd": "j"},
        "codes": {"city": {"杭州": "101210100"}},
    }
    # 自定义路径
    p1 = tmp_path / "b1.yaml"
    p1.write_text(yaml.safe_dump({**base_data, "logFile": "logs/test.log"}), encoding="utf-8")
    s1 = load_settings(p1)
    assert s1.log_file == tmp_path / "logs" / "test.log"

    # 留空禁用
    p2 = tmp_path / "b2.yaml"
    p2.write_text(yaml.safe_dump({**base_data, "logFile": ""}), encoding="utf-8")
    s2 = load_settings(p2)
    assert s2.log_file is None


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
