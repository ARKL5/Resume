"""本机 Chrome 持久会话与风控检测。"""

from __future__ import annotations

import json
import logging
import os
import random
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
            "/web/common/403.html",
            "/web/geek/safe-validate",
            "/web/geek/user-safe",
        )
    ):
        return True
    if "/web/user/" in url and "login" in url:
        return True
    try:
        geo = page.locator(
            ".geetest_panel, .geetest_holder, iframe[src*='geetest'], .boss-login-dialog"
        )
        for index in range(geo.count()):
            if geo.nth(index).is_visible():
                return True
    except Exception:
        return None
    return False


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
