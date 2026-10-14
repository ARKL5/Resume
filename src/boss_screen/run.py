"""流式岗位筛选。拉起本机 Chrome，按视口边滑边筛、当场点详情、实时写入 SQLite。"""

from __future__ import annotations

import logging
import random
import signal
import threading
import urllib.parse
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from boss_screen.ai import complete, jd_prompt, parse_jd, parse_title_action, title_prompt
from boss_screen.browser import detail_gap_seconds, fresh_page, halt_if_risk, needs_human, open_chrome, sleep_until
from boss_screen.cards import Card, ingest_job_list, overlay, parse_detail
from boss_screen.config import Settings, load_settings, search_url, setup_logging
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
MAX_DETAIL_FAIL_STREAK = 2


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

_LIST_CONTAINERS = ", ".join(
    [
        "ul.rec-job-list",
        "ul.job-list-box",
        ".job-list-box",
        ".search-job-result",
        "li.job-card-box",
        "li.job-card-wrapper",
    ]
)


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_file)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda _s, _f: stop.set())
    lock = take_lock()
    store = JobStore(settings.db_path)
    playwright = None
    context = None
    try:
        log.info(
            "流式筛选开始。详情上限 %s，onRisk=%s，数据库 %s",
            "无" if settings.detail_limit < 0 else settings.detail_limit,
            "stop" if settings.stop_on_risk else "wait",
            settings.db_path,
        )
        playwright, context = open_chrome(settings.browser_data)
        page = fresh_page(context)
        Session(settings, store, page, stop).execute()
    except KeyboardInterrupt:
        log.info("收到停止")
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        store.close()
        release(lock)
    log.info("筛选结束")


class Session:
    detail_attempts: int = 0
    detail_fail_streak: int = 0
    details_since_last_break: int = 0
    keyword_aborted: bool = False

    def __init__(self, settings: Settings, store: JobStore, page, stop: threading.Event) -> None:
        self.settings = settings
        self.store = store
        self.page = page
        self.stop = stop
        self.list_cards: dict[str, Card] = {}
        self.attempted_details: set[str] = set()
        self.detail_attempts = 0
        self.detail_fail_streak = 0
        self.details_since_last_break = 0
        self.keyword_aborted = False
        page.on("response", self._on_response)

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
            futures = [pool.submit(self._screen_job, str(row.get("keyword") or ""), row) for row in pending]
            for future in futures:
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
            try:
                self._keyword(keyword, base)
            except Exception as exc:
                if self.stop.is_set():
                    return
                log.error("【%s】处理失败，跳过该关键词：%s", keyword, exc)
            if index < len(keywords) - 1 and not self.stop.is_set():
                self._gap()

    def _keyword(self, keyword: str, base: str) -> None:
        self.list_cards.clear()
        self.keyword_aborted = False
        url = base + ("&" if "?" in base else "?") + "query=" + urllib.parse.quote_plus(keyword)
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
                if self.stop.is_set() or self.keyword_aborted or self._halt("Boss 列表页弹出人机验证或登录。"):
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

                if self.stop.is_set() or self.keyword_aborted:
                    break
                if consecutive_seen >= MAX_CONSECUTIVE_SEEN:
                    log.info("【%s】已连续遇到 %s 张已筛终局岗位，提前结束滚动", keyword, consecutive_seen)
                    break
                if (empty_scrolls >= 2 and self._footer_visible()) or empty_scrolls >= MAX_EMPTY_SCROLLS:
                    log.info("【%s】列表已到底部（累计处理 %s 张）", keyword, len(handled))
                    break

                if not self._scroll_step():
                    break

            for future in jd_futures:
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
                jd_futures.append(jd_pool.submit(self._screen_job, keyword, prior))
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
        for card, (action, reason) in zip(need_title_ai, outcomes, strict=True):
            if self.stop.is_set():
                return consecutive_seen
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

        self._click_details(keyword, to_click, jd_pool, jd_futures, stats)
        return consecutive_seen

    def _remaining_clicks(self) -> int:
        limit = self.settings.detail_limit
        return 2**31 - 1 if limit < 0 else max(0, limit - self.detail_attempts)

    def _title_ai(self, keyword: str, cards: list[Card]) -> list[tuple[str | None, str]]:
        if not cards:
            return []

        def one(card: Card) -> tuple[str | None, str]:
            prompt = title_prompt(self.settings, keyword, card.company, card.job, card.tags)
            try:
                raw = complete(self.settings, prompt)
            except Exception as exc:
                log.warning("标题AI失败 | %s | %s | %s", card.company, card.job, exc)
                return None, str(exc)
            return parse_title_action(raw)

        return _parallel("标题AI", cards, one, self.stop)

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
        for card in cards:
            if card.encrypt_id in attempted:
                continue
            if self._remaining_clicks() <= 0:
                break
            if self.stop.is_set() or self.keyword_aborted or self._halt("Boss 弹出人机验证或登录页。"):
                break
            target = self._card_locator(card.encrypt_id)
            if target is None:
                log.warning("视口附近未找到卡片，保持待点 | %s | %s", card.company, card.job)
                continue
            body = None
            try:
                # 一次详情点击至多尝试一次，避免超时后重复点击同一岗位。
                with self.page.expect_response(_is_detail, timeout=15_000) as waited:
                    self._human_click(target)
                    self.detail_attempts += 1
                    stats.detail_clicks += 1
                    attempted.add(card.encrypt_id)
                body = waited.value.text()
            except Exception:
                if self._halt("Boss 点详情时弹出验证。"):
                    break
            if body is None:
                stats.detail_fail += 1
                if self.stop.is_set():
                    break
                log.warning("等待岗位详情超时 | %s | %s", card.company, card.job)
                if self._on_detail_failure("Boss 连续等待岗位详情超时，多半是风控或页面卡住。"):
                    break
                self._pause_between_jobs()
                continue
            job = self._job_from_detail(card, body)
            if job is None:
                stats.detail_fail += 1
                if self.stop.is_set():
                    break
                if self._on_detail_failure("Boss 读不到岗位详情，多半是人机验证或页面卡住。"):
                    break
                self._pause_between_jobs()
                continue
            self.detail_fail_streak = 0
            stats.detail_ok += 1
            detail_rule = detail_rule_drop_reason(
                job["active"], job["recruiterTitle"], job["recruiter"], self.settings.black_recruiters
            )
            if detail_rule:
                self.store.upsert({**job, "keyword": keyword, "stage": "rule_drop", "reason": detail_rule})
                stats.rule_drops += 1
                log.info("rule_drop | %s | %s | %s", job["company"], job["job"], detail_rule)
                if self.stop.is_set():
                    continue
            else:
                # 第一时间把抓到的 JD 与公司详情落入 SQLite，防止后续中断或 AI 失败丢失点击成果
                stored = self.store.upsert({**job, "keyword": keyword})
                if self.stop.is_set():
                    continue
                jd_futures.append(jd_pool.submit(self._screen_job, keyword, stored or job))
            self._pause_between_jobs()
            if self._halt("Boss 弹出人机验证或登录页。"):
                break

    def _on_detail_failure(self, reason: str) -> bool:
        self.detail_fail_streak += 1
        log.warning("详情获取连续失败 (%s/%s)", self.detail_fail_streak, MAX_DETAIL_FAIL_STREAK)
        had_risk = needs_human(self.page)
        if self.detail_fail_streak < MAX_DETAIL_FAIL_STREAK and not had_risk:
            return False
        if self._halt(reason):
            return True
        if had_risk:
            self.detail_fail_streak = 0
            return False
        if self.detail_fail_streak > MAX_DETAIL_FAIL_STREAK:
            log.warning("跨关键词刷新后详情仍失败（连续 %s 次），停止本轮筛选以保护账号", self.detail_fail_streak)
            self.stop.set()
        else:
            log.warning("当前关键词连续 %s 次详情获取失败，提前结束该词并冷却", self.detail_fail_streak)
            self.keyword_aborted = True
        return True

    def _scroll_step(self) -> bool:
        try:
            delta = random.randint(520, 860)
            self.page.mouse.wheel(0, delta)
        except Exception as exc:
            if not _stale(exc):
                log.debug("滚动列表异常: %s", exc)
            return False
        return not self._sleep(random.uniform(3.2, 6.2))

    def _human_click(self, target) -> None:
        try:
            box = target.bounding_box()
            if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                tx = box["x"] + random.uniform(box["width"] * 0.25, box["width"] * 0.75)
                ty = box["y"] + random.uniform(box["height"] * 0.25, box["height"] * 0.75)
                self.page.mouse.move(tx, ty, steps=random.randint(8, 16))
                target.hover(timeout=2000)
                self._sleep(random.uniform(0.4, 0.9))
        except Exception:
            pass
        target.click()

    def _job_from_detail(self, card: Card, body: str) -> dict | None:
        parsed = parse_detail(body)
        job_name = parsed.get("job") or ""
        company = parsed.get("company") or ""
        if not job_name.strip() and not company.strip():
            log.warning("岗位详情解析为空 | %s | %s", card.company, card.job)
            return None
        href = self._detail_href() or card.href
        area = parsed.get("area") or card.area
        city = classify_city(area)
        if city == "其它" and is_search_city(classify_city(card.area)):
            city = classify_city(card.area)
        return {
            "encryptId": extract_encrypt_id(href) or card.encrypt_id,
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

    def _detail_href(self) -> str:
        try:
            more = self.page.locator("a.more-job-btn")
            if more.count() == 0:
                return ""
            href = more.first.get_attribute("href") or ""
            if href.startswith("/job_detail/"):
                return "https://www.zhipin.com" + href
        except Exception:
            return ""
        return ""

    def _screen_job(self, keyword: str, job: dict) -> str:
        try:
            raw = complete(self.settings, jd_prompt(self.settings, keyword, job))
        except Exception as exc:
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
            self.store.upsert(
                {
                    **job,
                    "keyword": keyword,
                    "stage": "ai_jd_pending",
                    "reason": ai_fail_reason("JD", reason),
                }
            )
            return "ai_jd_pending"
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

    def _on_response(self, response) -> None:
        try:
            url = response.url or ""
            if "/wapi/zpgeek/" not in url or "joblist" not in url:
                return
            body = response.text()
        except Exception:
            return
        for card in ingest_job_list(body or ""):
            self.list_cards[card.encrypt_id] = card

    def _harvest_new(self, handled: set[str]) -> list[Card]:
        by_id: dict[str, Card] = {}
        try:
            raw = self.page.evaluate(_HARVEST_JS)
        except Exception as exc:
            log.debug("收取列表卡片失败: %s", exc)
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
                by_id[encrypt_id] = overlay(nxt, extra) if extra is not None else nxt

        batch: list[Card] = []
        for encrypt_id, card in by_id.items():
            if encrypt_id in handled:
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
        last: Exception | None = None
        for attempt in (1, 2):
            try:
                self._goto(url)
                if self._risk_url():
                    self._halt("Boss 进入列表前弹出验证或登录。")
                    return
                self.page.wait_for_selector(_LIST_CONTAINERS, timeout=15_000)
                return
            except Exception as exc:
                if self.stop.is_set():
                    return
                last = exc
                log.warning("【%s】进入岗位列表失败（第%s/2次）：%s", keyword, attempt, exc)
                if attempt == 1:
                    self._sleep(3)
        raise RuntimeError(str(last or "岗位列表未出现"))

    def _goto(self, url: str) -> None:
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as first:
            if _landed(self.page, url):
                self._settle()
                return
            log.warning("导航失败，1秒后重试一次：%s", first)
            self._sleep(1)
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            except Exception:
                if not _landed(self.page, url):
                    raise
        self._settle()

    def _settle(self) -> None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass
        self._sleep(random.uniform(2.0, 3.5))

    def _card_locator(self, encrypt_id: str):
        if not valid_encrypt_id(encrypt_id):
            return None
        try:
            hit = self.page.locator("ul.rec-job-list li.job-card-box").filter(
                has=self.page.locator(f"a[href*='/job_detail/{encrypt_id}']")
            )
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
        return halt_if_risk(self.page, self.stop, self.settings.stop_on_risk, reason)

    def _risk_url(self) -> bool:
        return needs_human(self.page)

    def _footer_visible(self) -> bool:
        try:
            footer = self.page.locator("div#footer, #footer")
            return footer.count() > 0 and footer.first.is_visible()
        except Exception:
            return False

    def _gap(self) -> None:
        base = self.settings.keyword_gap
        jittered = random.uniform(base * 0.8, base * 1.3) if base > 0 else 0
        log.info("词间冷却 %.1f 秒", jittered)
        self._sleep(jittered)

    def _sleep(self, seconds: float) -> bool:
        return sleep_until(self.stop, seconds)


def _parallel(label: str, cards: list[Card], fn, stop: threading.Event) -> list[tuple[str | None, str]]:
    log.info("%s 并行 %s 张", label, len(cards))
    out: list[tuple[str | None, str]] = [(None, label + "未返回")] * len(cards)
    pool = ThreadPoolExecutor(max_workers=AI_PARALLELISM)
    try:
        futures = [pool.submit(fn, card) for card in cards]
        for index, future in enumerate(futures):
            if stop.is_set():
                future.cancel()
                continue
            try:
                out[index] = future.result()
            except Exception as exc:
                out[index] = (None, str(exc))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    return out


def _is_detail(response) -> bool:
    try:
        return "/wapi/zpgeek/job/detail.json" in (response.url or "") and response.request.method == "GET"
    except Exception:
        return False


def _landed(page, target: str) -> bool:
    try:
        current = page.url or ""
    except Exception:
        return False
    return current.startswith(target.split("?", 1)[0])


def _stale(exc: Exception) -> bool:
    message = str(exc)
    return "Object doesn't exist" in message or "Execution context was destroyed" in message
