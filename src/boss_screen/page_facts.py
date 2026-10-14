"""Boss 接口契约与当前页面的响应事实；回调只记事实，不在回调里暂停。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from boss_screen.cards import Card, ingest_job_list, parse_detail
from boss_screen.rules import valid_encrypt_id

# Boss 业务码到处置提示的映射；命中时把服务器诊断一并写进日志，值守不必再手抠接口。
RISK_CODES: dict[int, str] = {
    31: "疑似风控拦截页，需在浏览器完成验证",
    35: "疑似出口 IP 被标记异常，建议更换出口 IP 或等待冷却",
    36: "疑似账号或会话风控，需在浏览器完成验证",
    37: "疑似浏览器环境被判定异常，建议换出口或稍后重试",
}
# 可以在浏览器内验证后自行恢复的码；35 是 IP 级标记，验证没用，必须人工换出口。
VERIFICATION_CODES = frozenset({31, 36, 37})
CODE_MESSAGE_LIMIT = 60
# 单次请求失败只当噪声；连续这么多次失败才认为业务真的断了。
REQUEST_FAILURE_STREAK = 3


class ApiError(ValueError):
    """Boss 接口契约错误。hint 给值守处置方向，retryable 表示重载页面可能自愈。"""

    def __init__(
        self,
        reason: str,
        *,
        hint: str = "",
        verification: bool = False,
        retryable: bool = False,
    ):
        super().__init__(reason)
        self.hint = hint
        self.verification = verification
        self.retryable = retryable


def endpoint(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname != "www.zhipin.com":
        return ""
    return {
        "/wapi/zpgeek/search/joblist.json": "list",
        "/wapi/zpgeek/job/detail.json": "detail",
    }.get(parsed.path, "")


def business_data(body: str, status: int = 200) -> dict:
    if status != 200:
        raise ApiError(f"岗位接口 HTTP {status}", retryable=status == 429 or status >= 500)
    try:
        root = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise ApiError("岗位接口不是 JSON") from exc
    if not isinstance(root, dict) or type(root.get("code")) is not int or root["code"] != 0:
        code = root.get("code") if isinstance(root, dict) else None
        # 只写 code 与服务器的诊断文案（如「您的IP地址存在异常行为」）；zpData 里的安全参数不落日志。
        message = _code_message(root)
        code_text = f"岗位接口业务码 {code}" if code is not None else "岗位接口缺少业务码"
        raise ApiError(
            f"{code_text}（{message}）" if message else code_text,
            hint=RISK_CODES.get(code, "") if isinstance(code, int) else "",
            verification=code in VERIFICATION_CODES,
        )
    data = root.get("zpData")
    if not isinstance(data, dict):
        raise ApiError("岗位接口缺少 zpData")
    return data


def _code_message(root: object) -> str:
    if not isinstance(root, dict):
        return ""
    raw = root.get("message")
    if not isinstance(raw, str):
        return ""
    text = raw.replace("\n", " ").strip()
    return text[:CODE_MESSAGE_LIMIT]


@dataclass
class Fault:
    reason: str
    kind: str
    serial: int
    verification: bool = False
    hint: str = ""
    # 重载或重试可能自愈的故障；IP/环境风控码不是，重载只会白撞。
    retryable: bool = False


class PageFacts:
    def __init__(self, page):
        self.page = page
        self.generation = 0
        self.requests: dict[int, int] = {}
        self.serial = 0
        self.reset()
        page.on("request", self.on_request)
        page.on("response", self.on_response)
        page.on("requestfailed", self.on_failed)

    def reset(self) -> None:
        self.generation += 1
        self.requests.clear()
        self.cards: dict[str, Card] = {}
        self.details: dict[str, str] = {}
        self.detail_versions: dict[str, int] = {}
        self.has_more: bool | None = None
        self.list_serial = 0
        self.fault: Fault | None = None
        self.failed_streak = 0

    def fail(
        self,
        reason: str,
        kind: str = "list",
        verification: bool = False,
        *,
        hint: str = "",
        retryable: bool = False,
    ) -> None:
        self.serial += 1
        self.fault = Fault(reason, kind, self.serial, verification, hint, retryable)

    def on_request(self, request) -> None:
        if endpoint(request.url):
            self.requests[id(request)] = self.generation

    def on_failed(self, request) -> None:
        generation = self.requests.pop(id(request), None)
        if generation != self.generation:
            return
        # 单次失败常见于切页/导航竞态；连续失败才认定业务断了。
        self.failed_streak += 1
        if self.failed_streak >= REQUEST_FAILURE_STREAK:
            self.fail("岗位接口网络请求失败", endpoint(request.url), retryable=True)

    def on_response(self, response) -> None:
        kind = endpoint(response.url)
        if not kind:
            return
        generation = self.requests.pop(id(response.request), None)
        if generation != self.generation:
            return
        try:
            body = response.text()
            if generation != self.generation:
                return
            data = business_data(body, response.status)
            if kind == "list":
                items = data.get("jobList")
                if not isinstance(items, list) or type(data.get("hasMore")) is not bool:
                    raise ApiError("列表缺少 jobList 或 hasMore")
                cards = ingest_job_list(body)
                if len(cards) != len(items) or (not cards and data["hasMore"]):
                    raise ApiError("列表岗位事实不完整或异常空列表")
                self.serial += 1
                self.cards.update((c.encrypt_id, c) for c in cards)
                self.has_more = data["hasMore"]
                self.list_serial = self.serial
                self.failed_streak = 0
            else:
                parsed = parse_detail(body)
                ident = parsed["encryptId"]
                if not valid_encrypt_id(ident) or not parsed["job"] or not parsed["jd"]:
                    raise ApiError("详情缺少岗位身份、标题或正文")
                self.serial += 1
                self.details[ident] = body
                self.detail_versions[ident] = self.serial
                self.failed_streak = 0
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ApiError) else "岗位接口读取失败"
            self.fail(
                reason,
                kind,
                isinstance(exc, ApiError) and exc.verification,
                hint=exc.hint if isinstance(exc, ApiError) else "",
                retryable=isinstance(exc, ApiError) and exc.retryable,
            )
