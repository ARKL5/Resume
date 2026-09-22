"""列表规则、城市分页、停因。"""

from __future__ import annotations

import re

RECRUITER_TOKENS = ("猎头", "招聘顾问", "驻场")
PLACED_STAGES = frozenset(
    {
        "rule_drop",
        "ai_title_drop",
        "ai_title_pending",
        "ai_jd_drop",
        "jd_wait",
        "jd_wait_other",
        "ai_jd_pending",
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


def has_hr_active_copy(active: str | None) -> bool:
    if not active or not active.strip():
        return False
    text = active.strip()
    if text.lower() in ("true", "false"):
        return False
    markers = ("在线", "刚刚", "今日", "今天", "日", "天", "周", "月", "年", "未上线")
    return any(marker in text for marker in markers)


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
    if not black_recruiters:
        return None
    for raw in (recruiter_title, recruiter_name):
        if not raw or not raw.strip():
            continue
        if any(item and item in raw for item in black_recruiters):
            term = _matched_term(black_recruiters, raw)
            return "招聘者黑名单命中" + (f"：{term}" if term else "")
    return None


def rule_drop_reason(
    job_name: str | None,
    company: str | None,
    active: str | None,
    recruiter_title: str | None,
    recruiter_name: str | None,
    *,
    black_jobs: list[str] | None,
    black_companies: list[str] | None,
    black_recruiters: list[str] | None,
    company_tokens: list[str] | None,
    job_tokens: list[str] | None,
) -> str | None:
    if has_hr_active_copy(active) and not is_active_within_3_days(active):
        return "HR未近3天活跃：" + (active or "").strip()
    if job_name and black_jobs and any(item and item in job_name for item in black_jobs):
        term = _matched_term(black_jobs, job_name)
        return "职位黑名单命中" + (f"：{term}" if term else "")
    if company and black_companies and any(item and item in company for item in black_companies):
        term = _matched_term(black_companies, company)
        return "公司黑名单命中" + (f"：{term}" if term else "")
    company_token = first_token(company, company_tokens)
    if company_token:
        return f"公司名含：{company_token}"
    job_token = first_token(job_name, job_tokens)
    if job_token:
        return f"岗位名含：{job_token}"
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


def row_key(encrypt_id: str | None, company: str | None, job: str | None) -> str:
    if encrypt_id and encrypt_id.strip():
        return "id:" + encrypt_id.strip()
    name = f"{company or ''}|{job or ''}"
    if name == "|":
        return ""
    return "name:" + name


def is_placed_row(row: dict | None) -> bool:
    if not row:
        return False
    stage = str(row.get("stage") or "").strip()
    city = str(row.get("cityPage") or "").strip()
    return stage in PLACED_STAGES and city in CITY_PAGES


def strip_reason_body(raw: str | None) -> str:
    if not raw:
        return ""
    return re.sub(r"^(规则|AI 标题|AI JD)\s+", "", raw.strip()).strip()


def rule_reason(rule: str | None) -> str:
    body = strip_reason_body(rule)
    return "规则 " + (body or "未写明")


def ai_title_reason(reason: str | None) -> str:
    body = strip_reason_body(reason)
    return "AI 标题 " + (body or "无理由")


def ai_jd_reason(reason: str | None) -> str:
    body = strip_reason_body(reason)
    return "AI JD " + (body or "无理由")


def _shorten(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[:limit]


def ai_fail_reason(phase: str, reason: str | None) -> str:
    raw = "" if reason is None else reason.replace("\n", " ").strip()
    if not raw:
        return f"AI {phase} 失败或无法解析"
    body = strip_reason_body(raw)
    rest = body or raw
    if (
        "状态码" in raw
        or raw.startswith("AI请求")
        or "upstream" in raw
        or "auth_unavailable" in raw
    ):
        return f"AI {phase} 失败：" + _shorten(rest)
    return f"AI {phase} 无法解析：" + _shorten(rest)


def is_pending_click(reason: str | None) -> bool:
    text = reason or ""
    return "将点详情" in text or "详情上限" in text


def with_stored_hr_drop(row: dict) -> dict:
    """保留上已存的活跃文案不是近 3 天时，内存里改判为规则淘汰。不写文件。"""
    if row.get("stage") != "ai_keep":
        return row
    active = str(row.get("active") or "")
    if not (has_hr_active_copy(active) and not is_active_within_3_days(active)):
        return row
    copied = dict(row)
    copied["stage"] = "rule_drop"
    copied["reason"] = rule_reason("HR未近3天活跃：" + active.strip())
    copied["hrDrop"] = True
    return copied


def next_step(row: dict | None, city_page: str, list_rule: str | None, remaining: int) -> str:
    """再次出现时的下一步：skip、reclass、rule、title、click、jd、leave。"""
    if row is not None:
        judged = with_stored_hr_drop(row)
        if judged is not row and str(judged.get("stage") or "") == "rule_drop":
            return "reclass"
        if str(judged.get("stage") or "") in TERMINAL_STAGES:
            return "skip"
    if list_rule:
        return "rule"
    if row is None:
        return "title"
    stage = str(row.get("stage") or "")
    if stage == "jd_wait_other":
        return "title" if is_search_city(city_page) else "leave"
    if stage == "ai_title_pending":
        return "title"
    if stage == "ai_jd_pending":
        if str(row.get("jd") or "").strip():
            return "jd"
        return "click" if remaining > 0 else "leave"
    if stage == "jd_wait" and is_pending_click(str(row.get("reason") or "")):
        return "click" if remaining > 0 else "leave"
    if stage == "jd_wait":
        return "leave"
    return "title"


def jd_retry_city(job: dict) -> str:
    return classify_city(str(job.get("area") or ""))


def saved_jd_job(
    row: dict,
    *,
    job: str,
    company: str,
    area: str,
    href: str,
    encrypt_id: str,
) -> dict:
    """跨轮重试 JD。正文用已存的，学历经验行业规模融资和招聘者头衔空着。"""
    return {
        "job": job or str(row.get("job") or ""),
        "company": company or str(row.get("company") or ""),
        "salary": str(row.get("salary") or ""),
        "area": area or str(row.get("area") or ""),
        "recruiter": str(row.get("recruiter") or ""),
        "recruiterTitle": "",
        "active": str(row.get("active") or ""),
        "href": href or str(row.get("href") or ""),
        "encryptId": encrypt_id or str(row.get("encryptId") or ""),
        "jd": str(row.get("jd") or ""),
        "degree": "",
        "experience": "",
        "industry": "",
        "scale": "",
        "financing": "",
    }


def title_disposition(
    action: str | None,
    reason: str | None,
    city_page: str,
    remaining_clicks: int,
) -> tuple[str, str, bool]:
    """返回 stage、停因、是否占用一次详情点击。"""
    if action is None:
        return "ai_title_pending", ai_fail_reason("标题", reason), False
    if action == "drop":
        return "ai_title_drop", ai_title_reason(reason), False
    if not is_search_city(city_page):
        labeled = ai_title_reason(reason)
        return "jd_wait_other", f"{labeled}；工作地「{city_page}」，本轮不点详情", False
    if action == "park":
        return "jd_wait", ai_title_reason(reason), False
    labeled = ai_title_reason(reason)
    if remaining_clicks > 0:
        return "jd_wait", labeled + "；将点详情", True
    return "jd_wait", labeled + "；本轮详情上限", False


def join_area(*parts: str | None) -> str:
    kept = [part.strip() for part in parts if part and part.strip()]
    return "·".join(kept)


def slug(raw: str | None) -> str:
    if not raw or not raw.strip():
        return "na"
    text = re.sub(r"[\\/:*?\"<>|\s]+", "-", raw.strip())
    text = re.sub(r"-+", "-", text).strip("-")
    if len(text) > 80:
        text = text[:80]
    return text or "na"
