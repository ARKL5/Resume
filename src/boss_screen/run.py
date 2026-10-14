"""流式岗位筛选。拉起本机 Chrome，按视口边滑边筛、当场点详情、实时写入 SQLite。"""

from __future__ import annotations

import logging
import random
import signal
import threading
import time
import urllib.parse
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from boss_screen.ai import (
    complete,
    is_retryable,
    jd_prompt,
    parse_jd,
    parse_title_action,
    title_prompt,
)
from boss_screen.browser import detail_gap_seconds, fresh_page, open_chrome, risk_state
from boss_screen.cards import Card, overlay, parse_detail
from boss_screen.config import Settings, load_settings, search_url, setup_logging
from boss_screen.page_facts import PageFacts, business_data
from boss_screen.proc_lock import release, take_lock
from boss_screen.rules import (
    ai_fail_reason,
    classify_city,
    detail_rule_drop_reason,
    extract_encrypt_id,
    is_search_city,
    next_step,
    rule_drop_reason,
    title_disposition,
    valid_encrypt_id,
)
from boss_screen.store import JobStore

log = logging.getLogger("boss_screen")

AI_PARALLELISM = 16
MAX_SCROLL_ROUNDS = 30
MAX_CONSECUTIVE_SEEN = 25
MAX_EMPTY_SCROLLS = 4
# 熔断看滑动窗口而不是连续计数：上游 429/超时这类可重试失败之间夹着成功就不停轮。
AI_BREAKER_WINDOW = 12
AI_BREAKER_MIN_SAMPLES = 8
AI_BREAKER_FAIL_RATIO = 0.75
# 确定性失败（配置/鉴权类）不会自愈，连续几次就停。
MAX_DETERMINISTIC_AI_FAILS = 3
# 暂停期间自己重载目标页制造新的成功响应；风控码与验证页不碰。
SELF_RECOVERY_INTERVAL_SECONDS = 25.0
MAX_SELF_RECOVERY_ATTEMPTS = 5


def _release_hint(automatic: bool) -> str:
    return "验证后自动确认业务" if automatic else "处理后发送 SIGUSR1 明确继续"


@dataclass
class KeywordStats:
    cards: int = 0
    skipped: int = 0
    rule_drops: int = 0
    title_queued: int = 0
    title_park: int = 0
    title_drop: int = 0
    title_fail: int = 0
    detail_clicks: int = 0
    detail_ok: int = 0
    detail_fail: int = 0
    jd_keep: int = 0
    jd_drop: int = 0
    jd_fail: int = 0

_HARVEST_JS = """
() => Array.from(document.querySelectorAll('ul.rec-job-list li.job-card-box')).map(el => {
  const a = el.querySelector('a.job-name');
  const loc = el.querySelector('span.company-location');
  const name = el.querySelector('span.boss-name');
  const sal = el.querySelector('span.job-salary');
  return {
    job: (a && a.innerText ? a.innerText : '').trim(),
    company: (name && name.innerText ? name.innerText : '').trim(),
    area: (loc && loc.innerText ? loc.innerText : '').trim(),
    salary: (sal && sal.innerText ? sal.innerText : '').trim(),
    href: (a && a.getAttribute('href')) ? a.getAttribute('href') : ''
  };
})
"""

def main() -> int:
    settings = load_settings()
    setup_logging(settings.log_file)
    stop = threading.Event()
    resume = threading.Event()
    signal.signal(signal.SIGINT, lambda _s, _f: stop.set())
    signal.signal(signal.SIGTERM, lambda _s, _f: stop.set())
    signal.signal(signal.SIGUSR1, lambda _s, _f: resume.set())
    lock = take_lock()
    store = None
    playwright = context = None
    session = None
    result = "异常"
    try:
        store = JobStore(settings.db_path)
        log.info(
            "流式筛选开始。详情上限 %s，onRisk=%s，数据库 %s",
            "无" if settings.detail_limit < 0 else settings.detail_limit,
            "stop" if settings.stop_on_risk else "wait",
            settings.db_path,
        )
        playwright, context = open_chrome(settings.browser_data)
        session = Session(settings, store, fresh_page(context), stop, resume)
        session.execute()
        result = session.end_reason or ("人工停止" if stop.is_set() else "完成")
    except KeyboardInterrupt:
        result = "人工停止"
    except Exception:
        log.exception("筛选异常退出")
    finally:
        for close in (
            context.close if context is not None else None,
            playwright.stop if playwright is not None else None,
            store.close if store is not None else None,
        ):
            if close is not None:
                try:
                    close()
                except Exception:
                    result = "异常"
                    log.exception("筛选收尾失败")
        log.info("筛选结果：%s", result)
        release(lock)
    return 0 if result == "完成" else 2



class Session:
    detail_attempts: int = 0
    ai_deterministic_fails: int = 0
    details_since_last_break: int = 0

    def __init__(
        self, settings: Settings, store: JobStore, page, stop: threading.Event,
        resume: threading.Event | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.page = page
        self.stop = stop
        self.facts = PageFacts(page)
        self.list_cards = self.facts.cards
        self.resume = resume if resume is not None else threading.Event()
        self.end_reason = ""
        self.target_url = ""
        self.target_detail = ""
        self._pausing = False
        self._ai_lock = threading.Lock()
        self.pending_cards: dict[str, Card] = {}
        self.attempted_details: set[str] = set()
        self.detail_attempts = 0
        self.ai_deterministic_fails = 0
        self.ai_outcomes: deque[bool] = deque(maxlen=AI_BREAKER_WINDOW)
        self.details_since_last_break = 0

    def _attempted(self) -> set[str]:
        attempted = getattr(self, "attempted_details", None)
        if attempted is None:
            attempted = set()
            self.attempted_details = attempted
        return attempted

    def execute(self) -> None:
        self._retry_pending_jds()
        codes = self.settings.city_codes
        for index, city_code in enumerate(codes):
            if self.stop.is_set():
                return
            self._city(city_code)
            if self.stop.is_set():
                return
            if index < len(codes) - 1:
                self._gap()

    def _retry_pending_jds(self) -> None:
        pending = self.store.pending_jd_rows()
        if not pending:
            return
        log.info("库内残留待评 JD %s 条，优先后台重评（零网页点击）", len(pending))
        pool = ThreadPoolExecutor(max_workers=AI_PARALLELISM)
        try:
            futures = [self._submit_jd(pool, str(row.get("keyword") or ""), row) for row in pending]
            for future in futures:
                while not future.done() and not self.stop.is_set():
                    self._sleep(0.1)
                if self.stop.is_set():
                    future.cancel()
                    continue
                try:
                    future.result()
                except Exception as exc:
                    log.warning("残留 JD 重试失败: %s", exc)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    def _city(self, city_code: str) -> None:
        base = search_url(self.settings, city_code)
        keywords = self.settings.keywords
        for index, keyword in enumerate(keywords):
            if self.stop.is_set():
                return
            self._keyword(keyword, base)
            if index < len(keywords) - 1 and not self.stop.is_set():
                self._gap()

    def _keyword(self, keyword: str, base: str) -> None:
        self.facts.reset()
        self.list_cards = self.facts.cards
        self.pending_cards.clear()
        self.target_detail = ""
        url = base + ("&" if "?" in base else "?") + "query=" + urllib.parse.quote_plus(keyword)
        self.target_url = url
        self._open_list(keyword, url)
        if self.stop.is_set():
            return
        self._stream_list(keyword)

    def _stream_list(self, keyword: str) -> None:
        handled: set[str] = set()
        consecutive_seen = 0
        empty_scrolls = 0
        jd_futures: list[Future] = []
        stats = KeywordStats()

        jd_pool = ThreadPoolExecutor(max_workers=AI_PARALLELISM)
        try:
            for round_idx in range(MAX_SCROLL_ROUNDS):
                if self.stop.is_set() or self._halt("Boss 列表页弹出人机验证或登录。"):
                    break
                batch = self._harvest_new(handled)
                if batch:
                    empty_scrolls = 0
                    stats.cards = len(handled)
                    log.info("【%s】第 %s 屏收获新卡片 %s 张（累计 %s 张）", keyword, round_idx + 1, len(batch), len(handled))
                    consecutive_seen = self._process_batch(
                        keyword, batch, consecutive_seen, jd_pool, jd_futures, stats
                    )
                else:
                    empty_scrolls += 1

                if self.stop.is_set() or self._halt("列表事实收取后检查"):
                    break
                if consecutive_seen >= MAX_CONSECUTIVE_SEEN:
                    log.info("【%s】已连续遇到 %s 张已筛终局岗位，提前结束滚动", keyword, consecutive_seen)
                    break
                if empty_scrolls and self.facts.has_more is False and not self.pending_cards:
                    log.info("【%s】列表接口确认结束（累计处理 %s 张）", keyword, len(handled))
                    break
                if empty_scrolls >= MAX_EMPTY_SCROLLS:
                    self.facts.fail("列表持续无进展或待点卡片未出现")
                    if self._halt("列表加载异常"):
                        break
                    empty_scrolls = 0

                if not self._scroll_step():
                    break
            else:
                log.info("【%s】达到滚动预算 %s 次，结束该词", keyword, MAX_SCROLL_ROUNDS)

            for future in jd_futures:
                while not future.done() and not self.stop.is_set():
                    self._sleep(0.1)
                if self.stop.is_set():
                    future.cancel()
                    continue
                try:
                    outcome = future.result()
                    if outcome == "ai_keep":
                        stats.jd_keep += 1
                    elif outcome == "ai_jd_drop":
                        stats.jd_drop += 1
                    elif outcome == "ai_jd_pending":
                        stats.jd_fail += 1
                except Exception as exc:
                    stats.jd_fail += 1
                    log.warning("详情 AI 失败: %s", exc)
        finally:
            jd_pool.shutdown(wait=True, cancel_futures=True)

        log.info(
            "【%s】汇总：卡片 %s（终局跳过 %s）| 规则淘汰 %s | 标题[待点 %s/含糊 %s/淘汰 %s/失败 %s] | 详情[点击 %s/成功 %s/失败 %s] | JD[保留 %s/淘汰 %s/待补 %s]",
            keyword,
            stats.cards,
            stats.skipped,
            stats.rule_drops,
            stats.title_queued,
            stats.title_park,
            stats.title_drop,
            stats.title_fail,
            stats.detail_clicks,
            stats.detail_ok,
            stats.detail_fail,
            stats.jd_keep,
            stats.jd_drop,
            stats.jd_fail,
        )

    def _process_batch(
        self,
        keyword: str,
        batch: list[Card],
        consecutive_seen: int,
        jd_pool: ThreadPoolExecutor,
        jd_futures: list[Future],
        stats: KeywordStats | None = None,
    ) -> int:
        if stats is None:
            stats = KeywordStats()
        need_title_ai: list[Card] = []
        to_click: list[Card] = []
        attempted = self._attempted()

        for card in batch:
            if self.stop.is_set():
                return consecutive_seen
            prior = self.store.get(card.encrypt_id)
            city = classify_city(card.area)
            list_rule = rule_drop_reason(
                card.job, card.company, card.recruiter_title, card.recruiter, **self.settings.rule_kwargs()
            )
            remaining = self._remaining_clicks()
            step = next_step(prior, city, list_rule, remaining)
            if step == "skip":
                consecutive_seen += 1
                stats.skipped += 1
                continue
            consecutive_seen = 0
            if step == "leave":
                if prior is not None:
                    self.store.upsert({"encryptId": card.encrypt_id, "keyword": keyword})
                continue
            if step == "rule":
                self._write_card(keyword, card, "rule_drop", list_rule or "规则淘汰")
                stats.rule_drops += 1
                continue
            if step == "jd" and prior is not None:
                jd_futures.append(self._submit_jd(jd_pool, keyword, prior))
                continue
            if step == "click":
                if card.encrypt_id in attempted:
                    if prior is not None:
                        self.store.upsert({"encryptId": card.encrypt_id, "keyword": keyword})
                    continue
                to_click.append(card)
                continue
            need_title_ai.append(card)

        outcomes = self._title_ai(keyword, need_title_ai)
        for card, outcome in zip(need_title_ai, outcomes, strict=True):
            if outcome is None:
                continue  # 未开始或被取消，不制造一条假的 AI 失败记录。
            action, reason = outcome
            remaining = self._remaining_clicks()
            stage, clean_reason, should_click = title_disposition(
                action, reason, classify_city(card.area), remaining
            )
            self._write_card(keyword, card, stage, clean_reason)
            if stage == "jd_queued":
                stats.title_queued += 1
            elif stage == "jd_park":
                stats.title_park += 1
            elif stage == "ai_title_drop":
                stats.title_drop += 1
            elif stage == "ai_title_pending":
                stats.title_fail += 1
            if should_click and card.encrypt_id not in attempted:
                to_click.append(card)

        # 熔断只拦新工作；本批所有已完成结果先持久化，再决定是否继续操作网页。
        if not self.stop.is_set() and not self._halt("标题筛选完成后检查"):
            self._click_details(keyword, to_click, jd_pool, jd_futures, stats)
        return consecutive_seen

    def _remaining_clicks(self) -> int:
        limit = self.settings.detail_limit
        return 2**31 - 1 if limit < 0 else max(0, limit - self.detail_attempts)

    def _title_ai(self, keyword: str, cards: list[Card]) -> list[tuple[str | None, str] | None]:
        if not cards:
            return []

        def one(card: Card) -> tuple[str | None, str]:
            try:
                prompt = title_prompt(self.settings, keyword, card.company, card.job, card.tags)
                raw = complete(self.settings, prompt)
                action, reason = parse_title_action(raw)
            except Exception as exc:
                self._record_ai(False, retryable=is_retryable(exc))
                log.warning("标题AI失败 | %s | %s | %s", card.company, card.job, exc)
                return None, str(exc)
            # 回复看不懂是可重试的噪声，不该按确定性失败熔断。
            self._record_ai(action is not None, retryable=True)
            return action, reason

        return _parallel("标题AI", cards, one, self.stop, lambda: self._sleep(0.05))

    def _click_details(
        self,
        keyword: str,
        cards: list[Card],
        jd_pool: ThreadPoolExecutor,
        jd_futures: list[Future],
        stats: KeywordStats | None = None,
    ) -> None:
        if stats is None:
            stats = KeywordStats()
        attempted = self._attempted()
        body_cache = self.facts.details
        for card in cards:
            if card.encrypt_id in attempted:
                continue
            if self._remaining_clicks() <= 0:
                break
            self.target_detail = card.encrypt_id
            if self.stop.is_set() or self._halt("Boss 点详情前检查。"):
                break
            body = body_cache.get(card.encrypt_id)
            if body is None:
                target = self._card_locator(card.encrypt_id)
                if target is None:
                    self.pending_cards[card.encrypt_id] = card
                    log.warning("未找到岗位链接，保持待点 | %s | %s", card.company, card.job)
                    continue
                clicked = False
                try:
                    clicked = self._human_click(target)
                except Exception:
                    # 点击未完成不记为平台详情超时，也不重复点它。
                    self.facts.fail("岗位链接点击失败，需检查遮挡或页面变化", "detail")
                    if self._halt("点击未完成"):
                        break
                    self.pending_cards[card.encrypt_id] = card
                    continue
                if not clicked:
                    break
                self.detail_attempts += 1
                stats.detail_clicks += 1
                attempted.add(card.encrypt_id)
                list_before_wait = self.facts.list_serial
                deadline = time.monotonic() + 15
                while not self.stop.is_set() and time.monotonic() < deadline:
                    if self._halt("等待目标详情"):
                        break
                    body = body_cache.get(card.encrypt_id)
                    if body is not None:
                        break
                    self._sleep(0.2)
                # _sleep 内也可能完成恢复并跨过截止时间，出循环后再收一次已到达的正文。
                body = body_cache.get(card.encrypt_id)
                if body is None and not self.stop.is_set():
                    stats.detail_fail += 1
                    # 等待中已经恢复过列表时，不再为同一次详情失败重载第二遍。
                    if self.facts.list_serial == list_before_wait:
                        self.facts.fail("目标岗位详情未返回", "detail", retryable=True)
                        if self._halt("等待岗位详情超时"):
                            break
                        body = body_cache.get(card.encrypt_id)
            if body is None:
                if self.stop.is_set():
                    break
                self.pending_cards.pop(card.encrypt_id, None)
                self._write_card(keyword, card, "jd_queued", "详情未返回，保留待点，下轮再取")
                self._pause_between_jobs()
                continue
            attempted.add(card.encrypt_id)
            self.pending_cards.pop(card.encrypt_id, None)
            job = self._job_from_detail(card, body)
            if job is None:
                self.facts.fail("详情与目标岗位不一致或正文缺失", "detail")
                self._halt("详情关联失败")
                break
            stats.detail_ok += 1
            detail_rule = detail_rule_drop_reason(
                job["active"], job["recruiterTitle"], job["recruiter"], self.settings.black_recruiters
            )
            if detail_rule:
                self.store.upsert({**job, "keyword": keyword, "stage": "rule_drop", "reason": detail_rule})
                stats.rule_drops += 1
                log.info("rule_drop | %s | %s | %s", job["company"], job["job"], detail_rule)
            else:
                stored = self.store.upsert({**job, "keyword": keyword})
                if not self.stop.is_set():
                    jd_futures.append(self._submit_jd(jd_pool, keyword, stored or job))
            if self.stop.is_set():
                break
            self._pause_between_jobs()
        self.target_detail = ""

    def _scroll_step(self) -> bool:
        try:
            delta = random.randint(520, 860)
            self.page.mouse.wheel(0, delta)
        except Exception:
            self.facts.fail("列表滚动失败，需检查页面")
            return not self._halt("滚动失败")
        return not self._sleep(random.uniform(3.2, 6.2))

    def _human_click(self, target) -> bool:
        if self.stop.is_set() or self._halt("点击前检查"):
            return False
        target.scroll_into_view_if_needed(timeout=2000)
        box = target.bounding_box()
        if box is None or box["width"] <= 0 or box["height"] <= 0:
            raise RuntimeError("岗位链接不可见")
        position = {
            "x": random.uniform(box["width"] * 0.25, box["width"] * 0.75),
            "y": random.uniform(box["height"] * 0.25, box["height"] * 0.75),
        }
        target.hover(position=position, timeout=2000)
        if self._sleep(random.uniform(0.4, 0.9)):
            return False
        if self._halt("点击前检查"):
            return False
        target.click(position=position, timeout=5000)
        return True

    def _job_from_detail(self, card: Card, body: str) -> dict | None:
        try:
            business_data(body)
        except ValueError:
            return None
        parsed = parse_detail(body)
        job_name = parsed.get("job") or ""
        company = parsed.get("company") or ""
        if parsed.get("encryptId") != card.encrypt_id or not job_name or not parsed.get("jd"):
            return None
        href = f"https://www.zhipin.com/job_detail/{card.encrypt_id}.html"
        area = parsed.get("area") or card.area
        city = classify_city(area)
        if city == "其它" and is_search_city(classify_city(card.area)):
            city = classify_city(card.area)
        return {
            "encryptId": card.encrypt_id,
            "job": job_name or card.job,
            "company": company or card.company,
            "salary": parsed.get("salary") or card.salary,
            "area": area,
            "cityPage": city,
            "recruiter": parsed.get("recruiter") or card.recruiter,
            "recruiterTitle": parsed.get("recruiterTitle") or card.recruiter_title,
            "active": parsed.get("active") or "",
            "href": href,
            "tags": card.tags,
            "jd": parsed.get("jd") or "",
            "degree": parsed.get("degree") or card.degree,
            "experience": parsed.get("experience") or card.experience,
            "industry": parsed.get("industry") or card.industry,
            "scale": parsed.get("scale") or card.scale,
            "financing": parsed.get("financing") or card.financing,
        }

    def _record_ai(self, success: bool, *, retryable: bool = False) -> None:
        """每个 AI 尝试记一次账。可重试失败只进滑动窗口，确定性失败连续计数即熔断。"""
        with self._ai_lock:
            self.ai_outcomes.append(success)
            if success or retryable:
                self.ai_deterministic_fails = 0
            else:
                self.ai_deterministic_fails += 1
            reason = self._ai_breaker_reason()
            if reason and not self.stop.is_set():
                self.end_reason = "熔断"
                log.error("AI %s，停止本轮筛选", reason)
                self.stop.set()

    def _ai_breaker_reason(self) -> str:
        if self.ai_deterministic_fails >= MAX_DETERMINISTIC_AI_FAILS:
            return f"连续 {self.ai_deterministic_fails} 次确定性失败（配置或鉴权类，重试不会自愈）"
        window = list(self.ai_outcomes)
        if len(window) < AI_BREAKER_MIN_SAMPLES:
            return ""
        failed = window.count(False)
        if failed / len(window) >= AI_BREAKER_FAIL_RATIO:
            return (
                f"最近 {len(window)} 次调用失败 {failed} 次"
                f"（达到 {AI_BREAKER_FAIL_RATIO:.0%}，疑上游不可用）"
            )
        return ""

    def _submit_jd(self, pool: ThreadPoolExecutor, keyword: str, job: dict) -> Future:
        def work() -> str:
            if self.stop.is_set():
                return "ai_jd_pending"
            try:
                return self._screen_job(keyword, job)
            except Exception:
                # AI 失败已在 _screen_job 里记账；到这里是筛选自身的意外错误。
                self._record_ai(False)
                raise
        return pool.submit(work)

    def _screen_job(self, keyword: str, job: dict) -> str:
        try:
            raw = complete(self.settings, jd_prompt(self.settings, keyword, job))
        except Exception as exc:
            self._record_ai(False, retryable=is_retryable(exc))
            log.warning("JD AI失败 | %s | %s | %s", job.get("company"), job.get("job"), exc)
            self.store.upsert(
                {
                    **job,
                    "keyword": keyword,
                    "stage": "ai_jd_pending",
                    "reason": ai_fail_reason("JD", str(exc)),
                }
            )
            return "ai_jd_pending"
        keep, reason = parse_jd(raw)
        if keep is None:
            self._record_ai(False, retryable=True)
            self.store.upsert(
                {
                    **job,
                    "keyword": keyword,
                    "stage": "ai_jd_pending",
                    "reason": ai_fail_reason("JD", reason),
                }
            )
            return "ai_jd_pending"
        self._record_ai(True)
        stage = "ai_keep" if keep else "ai_jd_drop"
        clean_reason = reason.strip() or "无理由"
        log.info("%s | %s | %s | %s", stage, job.get("company"), job.get("job"), clean_reason)
        self.store.upsert(
            {
                **job,
                "keyword": keyword,
                "stage": stage,
                "reason": clean_reason,
            }
        )
        return stage

    def _pause_between_jobs(self) -> None:
        self.details_since_last_break += 1
        if self.details_since_last_break >= random.randint(5, 8):
            rest = random.randint(65, 115)
            log.info("拟真长休：已连续查看 %s 份详情，休息 %s 秒...", self.details_since_last_break, rest)
            self.details_since_last_break = 0
            self._sleep(rest)
            return

        seconds = detail_gap_seconds(self.settings.wait_time)
        log.info("详情阅读停顿 %s 秒", seconds)
        self._sleep(seconds)

    def _harvest_new(self, handled: set[str]) -> list[Card]:
        by_id: dict[str, Card] = dict(self.pending_cards)
        try:
            raw = self.page.evaluate(_HARVEST_JS)
        except Exception:
            self.facts.fail("列表 DOM 读取失败", retryable=True)
            raw = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                href = str(item.get("href") or "")
                encrypt_id = extract_encrypt_id(href)
                if not valid_encrypt_id(encrypt_id):
                    continue
                nxt = Card(
                    encrypt_id=encrypt_id,
                    job=str(item.get("job") or "").strip(),
                    company=str(item.get("company") or "").strip(),
                    salary=str(item.get("salary") or "").strip(),
                    area=str(item.get("area") or "").strip(),
                    href=href,
                )
                extra = self.list_cards.get(encrypt_id)
                if extra is not None:
                    by_id[encrypt_id] = overlay(extra, nxt)
                # DOM 可先于接口到达；等事实完整后才标为已处理。
        for encrypt_id, card in self.list_cards.items():
            by_id.setdefault(encrypt_id, card)

        batch: list[Card] = []
        for encrypt_id, card in by_id.items():
            if encrypt_id in handled and encrypt_id not in self.pending_cards:
                continue
            handled.add(encrypt_id)
            batch.append(card)
        return batch

    def _write_card(self, keyword: str, card: Card, stage: str, reason: str) -> None:
        self.store.upsert(
            {
                "encryptId": card.encrypt_id,
                "keyword": keyword,
                "company": card.company,
                "job": card.job,
                "salary": card.salary,
                "area": card.area,
                "cityPage": classify_city(card.area),
                "recruiter": card.recruiter,
                "recruiterTitle": card.recruiter_title,
                "href": card.href,
                "tags": card.tags,
                "degree": card.degree,
                "experience": card.experience,
                "industry": card.industry,
                "scale": card.scale,
                "financing": card.financing,
                "stage": stage,
                "reason": reason.strip() or "未写明",
            }
        )
        log.info("%s | %s | %s | %s", stage, card.company, card.job, reason)

    def _open_list(self, keyword: str, url: str) -> None:
        try:
            self._goto(url)
            deadline = time.monotonic() + 15
            while not self.stop.is_set() and self.facts.list_serial == 0 and time.monotonic() < deadline:
                if self._halt("进入列表"):
                    return
                self._sleep(0.2)
            if self.stop.is_set():
                return
            if self.facts.list_serial == 0:
                self.facts.fail("目标列表未返回成功响应", retryable=True)
            self._halt("进入列表")
        except Exception:
            self.facts.fail("列表导航或页面读取失败", retryable=True)
            self._halt("进入列表失败")

    def _goto(self, url: str) -> None:
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception:
            if not _landed(self.page, url) or self.facts.list_serial == 0:
                raise
        self._sleep(random.uniform(2.0, 3.5))

    def _card_locator(self, encrypt_id: str):
        if not valid_encrypt_id(encrypt_id):
            return None
        try:
            hit = self.page.locator(f"ul.rec-job-list a.job-name[href*='/job_detail/{encrypt_id}.html']")
            if hit.count() == 0:
                return None
            first = hit.first
            try:
                first.scroll_into_view_if_needed()
            except Exception:
                pass
            return first
        except Exception:
            return None

    def _halt(self, reason: str) -> bool:
        if self.stop.is_set():
            return True
        if self._pausing:
            return False
        self.facts.check_failures()
        state = risk_state(self.page)
        fault = self.facts.fault
        if state is False and fault is None:
            return False
        if self.settings.stop_on_risk:
            self.end_reason = "熔断"
            log.warning("风控或接口异常，停止本轮筛选：%s", fault.reason if fault else reason)
            self.stop.set()
            return True
        self._pausing = True
        self.resume.clear()
        serial = fault.serial if fault else self.facts.serial
        verification_seen = state is True
        automatic = bool(verification_seen or (fault and fault.verification))
        kind = fault.kind if fault else ("detail" if self.target_detail else "list")
        retryable = bool(fault and fault.retryable)
        allowed = automatic
        last_report: float | None = None
        report_mode = ""
        recoveries = 0
        next_recovery = time.monotonic() + SELF_RECOVERY_INTERVAL_SECONDS
        try:
            while not self.stop.is_set():
                self.facts.check_failures()
                state = risk_state(self.page)
                verification_seen |= state is True
                current = self.facts.fault
                if current is not None and current.serial > serial:
                    serial = current.serial
                    automatic = current.verification or verification_seen
                    kind = current.kind
                    retryable = current.retryable
                    allowed = automatic
                    self.resume.clear()
                    last_report = None
                if verification_seen and not automatic:
                    # 验证页可以晚于网络故障出现；出现过就把恢复交给人，避免重载打断验证。
                    automatic = allowed = True
                if self.resume.is_set():
                    allowed = True
                    self.resume.clear()
                detail_fresh = self.facts.detail_versions.get(self.target_detail, 0) > serial
                list_fresh = self.facts.list_serial > serial
                fresh = detail_fresh if kind == "detail" and self.target_detail else list_fresh
                # 仅自动重载过的瞬时故障可退回列表继续；保留目标身份，缺失正文由调用方显式留待下轮。
                list_recovered = retryable and recoveries > 0 and list_fresh
                if (
                    (fresh or list_recovered)
                    and (allowed or retryable)
                    and state is False
                    and _landed(self.page, self.target_url)
                ):
                    self.facts.fault = None
                    suffix = "（目标列表恢复，缺失详情留待下轮）" if kind == "detail" and not detail_fresh else ""
                    log.info("目标业务已恢复，继续%s", suffix)
                    return False
                can_retry = retryable and not automatic
                now = time.monotonic()
                if can_retry and recoveries < MAX_SELF_RECOVERY_ATTEMPTS and now >= next_recovery:
                    recoveries += 1
                    self._self_recover(recoveries)
                    next_recovery = time.monotonic() + SELF_RECOVERY_INTERVAL_SECONDS
                    continue  # 导航中可能收到新故障或验证页，先重新检查再报告。
                # 最后一次导航也要给业务响应留时间，不能刚发出请求就报预算耗尽。
                recovering = can_retry and (recoveries < MAX_SELF_RECOVERY_ATTEMPTS or now < next_recovery)
                mode = "recovering" if recovering else "human"
                if mode != report_mode or last_report is None or now - last_report >= 60:
                    if recovering:
                        log.info(
                            "自动恢复中：%s；已重载 %s/%s 次",
                            current.reason if current else reason, recoveries, MAX_SELF_RECOVERY_ATTEMPTS,
                        )
                    else:
                        log.warning(
                            "暂停等人：%s%s；%s；需在原浏览器恢复目标业务",
                            current.reason if current else reason,
                            f"（{current.hint}）" if current and current.hint else "",
                            _release_hint(automatic),
                        )
                    last_report, report_mode = now, mode
                try:
                    self.page.wait_for_timeout(250)
                except Exception:
                    # 页面已关闭也保持暂停；仍可用 SIGINT 干净结束。
                    self.stop.wait(0.25)
            return True
        finally:
            self._pausing = False

    def _self_recover(self, attempt: int) -> None:
        log.info("暂停自恢复 %s/%s：重新加载目标页", attempt, MAX_SELF_RECOVERY_ATTEMPTS)
        try:
            self._goto(self.target_url)
        except Exception as exc:
            log.warning("暂停自恢复导航失败：%s", exc)

    def _gap(self) -> None:
        base = self.settings.keyword_gap
        jittered = random.uniform(base * 0.8, base * 1.3) if base > 0 else 0
        log.info("词间冷却 %.1f 秒", jittered)
        self._sleep(jittered)

    def _sleep(self, seconds: float) -> bool:
        end = time.monotonic() + seconds
        while not self.stop.is_set():
            if self._halt("等待期间检查"):
                return True
            left = end - time.monotonic()
            if left <= 0:
                return False
            try:
                self.page.wait_for_timeout(min(left, 0.25) * 1000)
            except Exception:
                self.facts.fail("等待期间页面读取失败", retryable=True)
        return True


def _parallel(label: str, cards: list[Card], fn, stop: threading.Event, idle) -> list[tuple[str | None, str] | None]:
    log.info("%s 并行 %s 张", label, len(cards))

    def attempt(card: Card):
        return None if stop.is_set() else fn(card)

    pool = ThreadPoolExecutor(max_workers=AI_PARALLELISM)
    try:
        futures = [pool.submit(attempt, card) for card in cards]
        for future in futures:
            while not future.done() and not stop.is_set():
                idle()
            if stop.is_set():
                break
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    # 等所有在途任务收尾后再收结果，stop 不等于「丢弃已完成结果」。
    out: list[tuple[str | None, str] | None] = []
    for future in futures:
        if future.cancelled():
            out.append(None)
            continue
        try:
            out.append(future.result())
        except Exception as exc:
            out.append((None, str(exc)))
    return out


def _landed(page, target: str) -> bool:
    try:
        current = page.url or ""
    except Exception:
        return False
    if not target:
        return False
    actual = urllib.parse.urlsplit(current)
    expected = urllib.parse.urlsplit(target)
    return (
        (actual.scheme, actual.netloc, actual.path) == (expected.scheme, expected.netloc, expected.path)
        and urllib.parse.parse_qs(actual.query) == urllib.parse.parse_qs(expected.query)
    )

