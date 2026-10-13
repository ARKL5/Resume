"""标题三态与 JD 二值。只走 chat completions。"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from boss_screen.config import Settings, fill


def parse_title_action(raw: str | None) -> tuple[str | None, str]:
    obj, reason = _parse_reply(raw)
    action = obj.get("action")
    return (action if action in ("click", "park", "drop") else None), reason


def parse_jd(raw: str | None) -> tuple[bool | None, str]:
    obj, reason = _parse_reply(raw)
    keep = obj.get("keep")
    return (keep if isinstance(keep, bool) else None), reason


def _parse_reply(raw: str | None) -> tuple[dict, str]:
    if not raw:
        return {}, "空回复"
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict):
        return obj, str(obj.get("reason") or "")
    return {}, raw.replace("\n", " ").strip()[:200]


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
