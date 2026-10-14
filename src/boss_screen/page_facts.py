"""Boss 接口契约与当前页面的响应事实；回调只记事实，不在回调里暂停。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from boss_screen.cards import Card, ingest_job_list, parse_detail
from boss_screen.rules import valid_encrypt_id


class ApiError(ValueError):
    def __init__(self, reason: str, *, verification: bool = False):
        super().__init__(reason)
        self.verification = verification


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
        raise ApiError(f"岗位接口 HTTP {status}")
    try:
        root = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise ApiError("岗位接口不是 JSON") from exc
    if not isinstance(root, dict) or type(root.get("code")) is not int or root["code"] != 0:
        code = root.get("code") if isinstance(root, dict) else None
        # 不把原始响应或安全参数写入日志。
        raise ApiError(f"岗位接口业务码 {code!r}", verification=code in (35, 36))
    data = root.get("zpData")
    if not isinstance(data, dict):
        raise ApiError("岗位接口缺少 zpData")
    return data


@dataclass
class Fault:
    reason: str
    kind: str
    serial: int
    verification: bool = False


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

    def fail(self, reason: str, kind: str = "list", verification: bool = False) -> None:
        self.serial += 1
        self.fault = Fault(reason, kind, self.serial, verification)

    def on_request(self, request) -> None:
        if endpoint(request.url):
            self.requests[id(request)] = self.generation

    def on_failed(self, request) -> None:
        generation = self.requests.pop(id(request), None)
        if generation == self.generation:
            self.fail("岗位接口网络请求失败", endpoint(request.url))

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
            else:
                parsed = parse_detail(body)
                ident = parsed["encryptId"]
                if not valid_encrypt_id(ident) or not parsed["job"] or not parsed["jd"]:
                    raise ApiError("详情缺少岗位身份、标题或正文")
                self.serial += 1
                self.details[ident] = body
                self.detail_versions[ident] = self.serial
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ApiError) else "岗位接口读取失败"
            self.fail(reason, kind, isinstance(exc, ApiError) and exc.verification)
