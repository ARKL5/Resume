"""标题三态与 JD 二值。只走 chat completions。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from boss_screen.config import Settings, fill


def parse_title_action(raw: str | None) -> tuple[str | None, str]:
    if raw is None:
        return None, "空回复"
    reason = parse_reason(raw)
    try:
        obj = json.loads(_json_object(raw))
    except json.JSONDecodeError:
        return None, reason
    action = str(obj.get("action") or "").strip().lower()
    if action in ("click", "park", "drop"):
        return action, reason
    return None, reason


def parse_keep(raw: str | None) -> bool | None:
    if raw is None:
        return None
    try:
        obj = json.loads(_json_object(raw))
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict) and "keep" in obj:
        value = obj["keep"]
        if isinstance(value, bool):
            return value
    lower = raw.lower()
    if '"keep":true' in lower or '"keep": true' in lower:
        return True
    if '"keep":false' in lower or '"keep": false' in lower:
        return False
    return None


def parse_reason(raw: str | None) -> str:
    if raw is None:
        return "空回复"
    try:
        obj = json.loads(_json_object(raw))
        if isinstance(obj, dict) and "reason" in obj:
            return str(obj.get("reason") or "")
    except json.JSONDecodeError:
        pass
    text = raw.replace("\n", " ").strip()
    return text[:200]


def _json_object(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start : end + 1]
    return raw


def complete(settings: Settings, content: str) -> str:
    endpoint = settings.ai_base + "/chat/completions"
    payload = {
        "model": settings.ai_model,
        "temperature": 0.5,
        "messages": [{"role": "user", "content": content}],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + settings.ai_key,
            "api-key": settings.ai_key,
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
            obj = json.loads(raw)
            return obj["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            message = f"AI请求失败，状态码: {exc.code}, 详情: {detail}"
            if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(0.8 * attempt)
                last_error = RuntimeError(message)
                continue
            raise RuntimeError(message) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError) as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(0.8 * attempt)
                continue
            raise RuntimeError(str(exc)) from exc
    raise RuntimeError(str(last_error or "AI请求失败"))


def title_prompt(settings: Settings, keyword: str, company: str, job: str, tags: str) -> str:
    return fill(
        settings.title_prompt,
        {"keyword": keyword, "company": company, "job": job, "tags": tags},
    )


def jd_prompt(settings: Settings, keyword: str, job: dict) -> str:
    return fill(
        settings.jd_prompt,
        {
            "profile": settings.profile,
            "keyword": keyword,
            "company": job.get("company") or "",
            "job": job.get("job") or "",
            "recruiterTitle": job.get("recruiterTitle") or "",
            "area": job.get("area") or "",
            "degree": job.get("degree") or "",
            "experience": job.get("experience") or "",
            "industry": job.get("industry") or "",
            "scale": job.get("scale") or "",
            "stage": job.get("financing") or "",
            "jd": job.get("jd") or "",
        },
    )
