"""标题三态与 JD 二值。只走 chat completions。"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from boss_screen.config import Settings, fill

AI_ATTEMPTS = 4
AI_BACKOFF_SECONDS = 0.8
AI_MAX_BACKOFF_SECONDS = 8.0
AI_MAX_COOLDOWN_SECONDS = 20.0
# 上游过载类状态码：换个时机再来可能成功，不算确定性失败。
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class AiError(RuntimeError):
    """AI 调用失败。retryable 为真表示重试或稍后再试可能成功。"""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status: int | None = None,
        cooldown: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.cooldown = cooldown


def is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, AiError) and exc.retryable


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
    last_error: AiError | None = None
    for attempt in range(1, AI_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
            obj = json.loads(raw)
            return obj["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            cooldown = _cooldown_seconds(detail) if exc.code == 429 else None
            last_error = AiError(
                f"AI请求失败，状态码: {exc.code}, 详情: {detail}",
                retryable=exc.code in RETRYABLE_STATUS,
                status=exc.code,
                cooldown=cooldown,
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = AiError(f"AI请求失败，网络或超时: {exc}", retryable=True)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            last_error = AiError(f"AI回复不符合契约: {exc!r}", retryable=True)
        if not last_error.retryable or attempt == AI_ATTEMPTS:
            raise last_error
        time.sleep(_backoff(attempt, last_error.cooldown))
    raise last_error if last_error is not None else AiError("AI请求失败")


def _cooldown_seconds(detail: str) -> float | None:
    """网关给出的冷却秒数（重置时间），有就照着退避，别用固定退避硬撞。"""
    try:
        payload = json.loads(detail)
    except (ValueError, TypeError):
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None
    raw = error.get("reset_seconds")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0:
        return float(raw)
    return None


def _backoff(attempt: int, cooldown: float | None) -> float:
    if cooldown is not None:
        return min(cooldown + 0.5, AI_MAX_COOLDOWN_SECONDS) + random.uniform(0, 0.3)
    return min(AI_BACKOFF_SECONDS * (2 ** (attempt - 1)), AI_MAX_BACKOFF_SECONDS) + random.uniform(0, 0.3)


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
