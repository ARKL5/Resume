"""当场点名的代聊。筛选进程还在就拒绝。"""

from __future__ import annotations

import logging
import signal
import threading

from boss_screen.browser import detail_gap_seconds, fresh_page, halt_if_risk, open_chrome, sleep_until
from boss_screen.config import load_settings
from boss_screen.opened import append_opened, load_ids
from boss_screen.proc_lock import release, take_lock
from boss_screen.rules import valid_encrypt_id

log = logging.getLogger("boss_screen")

_CHAT_BUTTON = "a.btn-startchat, a.op-btn-chat"
_CHAT_INPUT = "div#chat-input.chat-input[contenteditable='true'], textarea.input-area"
_SEND = "div.send-message, button[type='send'].btn-send, button.btn-send"
_IMAGE_BOX = "div.btn-sendimg[aria-label='发送图片'], div[aria-label='发送图片'].btn-sendimg"


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    encrypt_ids, send_image = _parse_args(args)
    if not encrypt_ids:
        raise SystemExit("需要当场点名的 encryptId")
    settings = load_settings()
    if not settings.greeting:
        raise SystemExit("boss.yaml 的 greeting 为空")
    if send_image and not settings.resume_image.is_file():
        log.error("resume.jpg 不存在，这次仍发招呼，不发图")
        send_image = False
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda _s, _f: stop.set())
    lock = take_lock()
    playwright = None
    context = None
    try:
        log.info("代聊开始，%s 个，发图=%s", len(encrypt_ids), send_image)
        playwright, context = open_chrome(settings.browser_data)
        # 至少留一个页。关到零页时，持久上下文会把 Chrome 一起退出。
        keeper = fresh_page(context)
        seen = load_ids(settings.opened_chats)
        ok = _chat_all(context, settings, encrypt_ids, seen, send_image, stop)
        log.info("代聊结束，成功 %s / %s", ok, len(encrypt_ids))
    except KeyboardInterrupt:
        log.info("收到停止")
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        release(lock)


def button_action(text: str) -> str:
    raw = text.replace(" ", "").replace("\n", "")
    if "继续沟通" in raw:
        return "opened"
    if "立即沟通" in raw:
        return "send"
    return "absent"


def _parse_args(argv: list[str]) -> tuple[list[str], bool]:
    send_image = False
    ids: list[str] = []
    options = True
    for token in argv:
        if options and token == "--":
            options = False
            continue
        if options and token == "--image":
            send_image = True
            continue
        if options and token.startswith("-"):
            raise SystemExit(f"未知参数 {token}。以 - 开头的 encryptId 写在 -- 后面")
        text = token.strip()
        if text:
            ids.append(text)
    return ids, send_image


def first_visible_action(candidates: list[tuple[str, bool]]) -> tuple[str, int | None]:
    for index, (text, visible) in enumerate(candidates):
        if not visible:
            continue
        action = button_action(text)
        if action != "absent":
            return action, index
    return "absent", None


def next_chat_step(encrypt_id: str, seen: set[str]) -> str:
    if not valid_encrypt_id(encrypt_id):
        return "invalid"
    if encrypt_id in seen:
        return "skip"
    return "open"


def should_record(action: str, greeting_sent: bool) -> bool:
    if action == "opened":
        return True
    return action == "send" and greeting_sent


def _chat_all(context, settings, encrypt_ids: list[str], seen: set[str], send_image: bool, stop) -> int:
    ok = 0
    opened_detail = False
    for encrypt_id in encrypt_ids:
        if stop.is_set():
            break
        step = next_chat_step(encrypt_id, seen)
        if step == "invalid":
            log.warning("跳过非法 encryptId %s", encrypt_id)
            continue
        if step == "skip":
            log.info("已开聊，跳过 %s", encrypt_id)
            continue
        if opened_detail:
            seconds = detail_gap_seconds(settings.wait_time)
            log.info("岗位间停顿 %s 秒", seconds)
            if sleep_until(stop, seconds):
                break
        opened_detail = True
        if _chat_one(context, settings, encrypt_id, send_image, stop):
            ok += 1
            seen.add(encrypt_id)
    return ok


def _chat_one(context, settings, encrypt_id: str, send_image: bool, stop) -> bool:
    page = context.new_page()
    page.set_default_timeout(30_000)
    try:
        page.goto(
            f"https://www.zhipin.com/job_detail/{encrypt_id}.html",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        if halt_if_risk(page, stop, settings.stop_on_risk, encrypt_id):
            return False
        action, button = _wait_button(page, stop)
        if action == "absent":
            log.warning("未找到立即沟通按钮，跳过 %s", encrypt_id)
            return False
        if action == "opened" and should_record(action, False):
            append_opened(settings.opened_chats, encrypt_id)
            log.info("继续沟通，记已开聊并跳过 %s", encrypt_id)
            return True
        button.click()
        filled = _fill_and_send(page, settings.greeting, stop)
        if not should_record("send", filled):
            log.warning("代聊失败 %s: 没有发出招呼", encrypt_id)
            return False
        if send_image:
            _send_image(page, settings.resume_image)
        append_opened(settings.opened_chats, encrypt_id)
        log.info("已开聊 %s 招呼已发", encrypt_id)
        return True
    except Exception as exc:
        log.warning("代聊失败 %s: %s", encrypt_id, exc)
        return False
    finally:
        try:
            page.close()
        except Exception:
            pass


def _wait_button(page, stop):
    button = page.locator(_CHAT_BUTTON)
    for _ in range(5):
        if stop.is_set():
            return "absent", None
        try:
            count = button.count()
            candidates: list[tuple[str, bool]] = []
            for index in range(count):
                item = button.nth(index)
                visible = False
                text = ""
                try:
                    visible = bool(item.is_visible())
                except Exception:
                    visible = False
                try:
                    text = item.text_content() or ""
                except Exception:
                    text = ""
                candidates.append((text, visible))
            action, index = first_visible_action(candidates)
            if action != "absent" and index is not None:
                return action, button.nth(index)
        except Exception:
            pass
        if sleep_until(stop, 1):
            return "absent", None
    return "absent", None


def _fill_and_send(page, greeting: str, stop) -> bool:
    field = page.locator(_CHAT_INPUT)
    ready = None
    for _ in range(10):
        if stop.is_set():
            return False
        try:
            if field.count() > 0:
                ready = field.first
                break
        except Exception:
            pass
        if sleep_until(stop, 1):
            return False
    if ready is None:
        return False
    try:
        ready.click()
        tag = ready.evaluate("el => el.tagName.toLowerCase()")
        if tag == "textarea":
            ready.fill(greeting)
        else:
            ready.evaluate(
                "(el, msg) => { el.innerText = msg; el.dispatchEvent(new Event('input', { bubbles: true })); }",
                greeting,
            )
    except Exception:
        return False
    send = page.locator(_SEND)
    try:
        if send.count() == 0:
            return False
        send.first.click()
    except Exception:
        return False
    sleep_until(stop, 1)
    try:
        page.locator("i.icon-close").first.click(timeout=1_000)
    except Exception:
        pass
    return True


def _send_image(page, image) -> bool:
    if not image.is_file():
        log.error("resume.jpg 不存在，跳过发图")
        return False
    try:
        if "/web/geek/chat" not in (page.url or ""):
            button = page.locator(_CHAT_BUTTON)
            if button.count() == 0:
                log.warning("未找到沟通按钮，跳过发图")
                return False
            button.first.click()
            page.wait_for_url("**/web/geek/chat**", timeout=15_000)
        box = page.locator(_IMAGE_BOX)
        file_input = box.locator("input[type='file'][accept*='image']").first
        if file_input.count() == 0 and box.count() > 0:
            try:
                with page.expect_file_chooser(timeout=3_000) as chooser:
                    box.first.click()
                chooser.value.set_files(str(image))
                sleep_until(threading.Event(), 1)
                return True
            except Exception:
                sleep_until(threading.Event(), 1)
                file_input = box.locator("input[type='file'][accept*='image']").first
        file_input.wait_for(state="attached", timeout=10_000)
        file_input.set_input_files(str(image))
        sleep_until(threading.Event(), 1)
        return True
    except Exception as exc:
        log.error("发送图片简历失败：%s", exc)
        return False
