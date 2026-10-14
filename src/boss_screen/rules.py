"""筛选规则、城市分页与状态流转。"""

from __future__ import annotations

import re

RECRUITER_TOKENS = ("猎头", "招聘顾问", "驻场")
PLACED_STAGES = frozenset(
    {
        "rule_drop",
        "ai_title_drop",
        "ai_title_pending",
        "jd_park",
        "jd_queued",
        "ai_jd_pending",
        "ai_jd_drop",
        "ai_keep",
    }
)
CITY_PAGES = frozenset({"杭州", "上海", "其它"})
TERMINAL_STAGES = frozenset({"rule_drop", "ai_title_drop", "ai_jd_drop", "ai_keep"})
_ENCRYPT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def classify_city(area: str | None) -> str:
    text = area or ""
    if "杭州" in text:
        return "杭州"
    if "上海" in text:
        return "上海"
    return "其它"


def is_search_city(city_page: str) -> bool:
    return city_page in ("杭州", "上海")


def contains_job_token(text: str, token: str) -> bool:
    if token not in text:
        return False
    if token == "训练":
        return "训练" in text.replace("后训练", "")
    return True


def first_token(text: str | None, tokens: list[str] | None) -> str | None:
    if not text or not text.strip() or not tokens:
        return None
    for token in tokens:
        if token and contains_job_token(text, token):
            return token
    return None


def is_active_within_3_days(active: str | None) -> bool:
    if not active or not active.strip():
        return False
    text = active.strip()
    if "未上线" in text:
        return False
    markers = (
        "在线",
        "刚刚",
        "今日",
        "今天",
        "3日内",
        "2日内",
        "1日内",
        "3天内",
        "2天内",
        "1天内",
    )
    return any(marker in text for marker in markers)


def _matched_term(patterns: list[str] | None, text: str | None) -> str | None:
    if not patterns or not text:
        return None
    for pattern in patterns:
        if pattern and pattern in text:
            return pattern
    return None


def recruiter_drop_reason(
    recruiter_title: str | None,
    recruiter_name: str | None,
    black_recruiters: list[str] | None,
) -> str | None:
    token = first_token(recruiter_title, list(RECRUITER_TOKENS))
    if token:
        return f"招聘者含：{token}"
    for raw in (recruiter_title, recruiter_name):
        term = _matched_term(black_recruiters, raw)
        if term:
            return f"招聘者黑名单命中：{term}"
    return None


def rule_drop_reason(
    job_name: str | None,
    company: str | None,
    recruiter_title: str | None,
    recruiter_name: str | None,
    *,
    black_jobs: list[str] | None,
    black_companies: list[str] | None,
    black_recruiters: list[str] | None,
    company_tokens: list[str] | None,
    job_tokens: list[str] | None,
) -> str | None:
    term = _matched_term(black_jobs, job_name)
    if term:
        return f"职位黑名单命中：{term}"
    term = _matched_term(black_companies, company)
    if term:
        return f"公司黑名单命中：{term}"
    company_token = first_token(company, company_tokens)
    if company_token:
        return f"公司名含：{company_token}"
    job_token = first_token(job_name, job_tokens)
    if job_token:
        return f"岗位名含：{job_token}"
    return recruiter_drop_reason(recruiter_title, recruiter_name, black_recruiters)


def detail_rule_drop_reason(
    active: str | None,
    recruiter_title: str | None,
    recruiter_name: str | None,
    black_recruiters: list[str] | None,
) -> str | None:
    if not is_active_within_3_days(active):
        return "HR活跃度缺失或未近3天活跃：" + ((active or "未知").strip() or "未知")
    return recruiter_drop_reason(recruiter_title, recruiter_name, black_recruiters)


def valid_encrypt_id(value: str | None) -> bool:
    return bool(value and _ENCRYPT_ID.match(value))


def extract_encrypt_id(href: str | None) -> str:
    if not href or not href.strip():
        return ""
    key = "/job_detail/"
    idx = href.find(key)
    if idx < 0:
        return ""
    start = idx + len(key)
    end = href.find(".html", start)
    if end < 0:
        query = href.find("?", start)
        end = query if query >= 0 else len(href)
    encrypt_id = href[start:end].strip()
    if not encrypt_id or not _ENCRYPT_ID.match(encrypt_id):
        return ""
    return encrypt_id


def is_placed_row(row: dict | None) -> bool:
    if not row:
        return False
    encrypt_id = str(row.get("encryptId") or "").strip()
    stage = str(row.get("stage") or "").strip()
    city = str(row.get("cityPage") or "").strip()
    return valid_encrypt_id(encrypt_id) and stage in PLACED_STAGES and city in CITY_PAGES


def _shorten(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[:limit]


def ai_fail_reason(phase: str, reason: str | None) -> str:
    raw = "" if reason is None else reason.replace("\n", " ").strip()
    if not raw:
        return f"{phase}失败或无法解析"
    if (
        "状态码" in raw
        or raw.startswith("AI请求")
        or "upstream" in raw
        or "auth_unavailable" in raw
    ):
        return f"{phase}请求失败：" + _shorten(raw)
    return f"{phase}无法解析：" + _shorten(raw)


def next_step(row: dict | None, city_page: str, list_rule: str | None, remaining: int) -> str:
    """岗位在列表出现时的下一步：skip、rule、title、click、jd、leave。"""
    if row is not None and row.get("stage") in TERMINAL_STAGES:
        return "skip"
    if list_rule:
        return "rule"
    if row is None:
        return "title"
    stage = str(row.get("stage") or "")
    if stage == "ai_title_pending":
        return "title"
    if stage == "ai_jd_pending":
        if str(row.get("jd") or "").strip():
            return "jd"
        return "click" if (is_search_city(city_page) and remaining > 0) else "leave"
    if stage == "jd_queued":
        return "click" if (is_search_city(city_page) and remaining > 0) else "leave"
    if stage == "jd_park":
        return "leave"
    return "title"


def title_disposition(
    action: str | None,
    reason: str | None,
    city_page: str,
    remaining_clicks: int,
) -> tuple[str, str, bool]:
    """返回 (stage, reason, should_click_now)。"""
    if action is None:
        return "ai_title_pending", ai_fail_reason("标题", reason), False
    clean = (reason or "").strip() or "无理由"
    if action == "drop":
        return "ai_title_drop", clean, False
    if action == "park":
        return "jd_park", clean, False
    should_click = is_search_city(city_page) and remaining_clicks > 0
    return "jd_queued", clean, should_click


def join_area(*parts: str | None) -> str:
    kept = [part.strip() for part in parts if part and part.strip()]
    return "·".join(kept)
