"""本机 Chrome 持久会话与风控检测。"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from pathlib import Path

log = logging.getLogger("boss_screen")


def proxy_args(environ=None) -> list[str]:
    """让本机 Chrome 走本机代理。WSL 里 zhipin 只有代理可达，直连是空白页。"""
    env = os.environ if environ is None else environ
    proxy = env.get("https_proxy") or env.get("HTTPS_PROXY") or env.get("http_proxy") or env.get("HTTP_PROXY")
    if not proxy:
        return []
    return [f"--proxy-server={proxy}", "--proxy-bypass-list=localhost;127.0.0.1;::1"]


def open_chrome(user_data: Path):
    from patchright.sync_api import sync_playwright

    user_data.mkdir(parents=True, exist_ok=True)
    _clear_crash_exit(user_data)
    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(
        str(user_data),
        channel="chrome",
        headless=False,
        no_viewport=True,
        focus_control=False,
        slow_mo=50,
        args=[
            "--start-maximized",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-debugging-port=9222",
            *proxy_args(),
        ],
    )
    return playwright, context


def fresh_page(context):
    startup = list(context.pages)
    page = context.new_page()
    page.set_default_timeout(30_000)
    for old in startup:
        try:
            old.close()
        except Exception:
            pass
    return page


def detail_gap_seconds(wait_time: int) -> int:
    low = max(1, wait_time // 2)
    if low >= wait_time:
        return wait_time
    return random.randint(low, wait_time)


def sleep_until(stop: threading.Event, seconds: float) -> bool:
    """睡够返回 False。中途收到停止返回 True。"""
    end = time.monotonic() + seconds
    while not stop.is_set():
        left = end - time.monotonic()
        if left <= 0:
            return False
        if stop.wait(min(left, 1)):
            return True
    return True


def needs_human(page) -> bool:
    return risk_state(page) is True


def risk_state(page) -> bool | None:
    """True 是风控页，False 不是，None 是页面读失败。"""
    try:
        url = page.url or ""
    except Exception:
        return None
    if any(
        part in url
        for part in (
            "/web/user/safe/verify-slider",
            "/web/passport/zp/verify",
            "/web/passport/zp/security",
            "security-check",
        )
    ):
        return True
    if "/web/user/" in url and "login" in url:
        return True
    try:
        geo = page.locator(".geetest_panel, .geetest_holder, iframe[src*='geetest']")
        for index in range(geo.count()):
            try:
                if geo.nth(index).is_visible():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def halt_if_risk(
    page,
    stop: threading.Event,
    stop_on_risk: bool,
    reason: str,
    poll_seconds: float = 5,
) -> bool:
    """True 表示这一轮该结束。读不到页面不算验证已消失。"""
    state = risk_state(page)
    if state is None:
        if stop_on_risk:
            log.warning("读不到页面，停止：%s", reason)
            stop.set()
            return True
        log.warning("读不到页面，暂停等人：%s", reason)
    elif not state:
        return False
    elif stop_on_risk:
        log.warning("风控，停止：%s", reason)
        stop.set()
        return True
    else:
        log.warning("风控，暂停等人：%s", reason)
    polls = 0
    while not stop.is_set():
        if sleep_until(stop, poll_seconds):
            return True
        polls += 1
        state = risk_state(page)
        if state is None:
            if polls % 12 == 0:
                log.warning("读不到页面，暂停等人：%s", reason)
            continue
        if not state:
            log.info("验证已消失，继续")
            return False
        if polls % 12 == 0:
            log.warning("风控，暂停等人：%s", reason)
    return True


def _clear_crash_exit(user_data: Path) -> None:
    preferences = user_data / "Default" / "Preferences"
    if not preferences.is_file():
        return
    try:
        root = json.loads(preferences.read_text(encoding="utf-8"))
        profile = root.get("profile")
        if not isinstance(profile, dict):
            return
        if profile.get("exit_type") == "Normal" and profile.get("exited_cleanly") is True:
            return
        profile["exit_type"] = "Normal"
        profile["exited_cleanly"] = True
        preferences.write_text(json.dumps(root, ensure_ascii=False), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        log.warning("清理 Chrome 退出标记失败，继续启动")
