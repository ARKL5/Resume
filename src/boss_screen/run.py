"""长驻筛选。拉起本机 Chrome，滚列表，写 jsonl。没有 HTTP。代聊是另一条命令。"""

from __future__ import annotations

import logging
import random
import signal
import threading
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from boss_screen.ai import complete, jd_prompt, parse_keep, parse_reason, parse_title_action, title_prompt
from boss_screen.browser import detail_gap_seconds, fresh_page, halt_if_risk, needs_human, open_chrome, sleep_until
from boss_screen.cards import Card, ingest_job_list, overlay, parse_detail
from boss_screen.config import Settings, load_settings, screen_file_name, search_url, setup_logging
from boss_screen.proc_lock import release, take_lock
from boss_screen.rules import (
    ai_fail_reason,
    ai_jd_reason,
    classify_city,
    extract_encrypt_id,
    is_active_within_3_days,
    is_search_city,
    jd_retry_city,
    next_step,
    recruiter_drop_reason,
    row_key,
    rule_drop_reason,
    rule_reason,
    saved_jd_job,
    title_disposition,
    valid_encrypt_id,
    with_stored_hr_drop,
)
from boss_screen.store import ScreenLog, load_seen

log = logging.getLogger("boss_screen")

AI_PARALLELISM = 25
_HARVEST_JS = """
() => {
  const LINE = /^(在线|刚刚活跃|今日活跃|今天活跃|[1-3]日内活跃|[1-3]天内活跃|本周活跃|[0-9]+周内活跃|本月活跃|[0-9]+月内活跃|半年前活跃|近半年活跃|未上线)$/;
  const activeOf = (el) => {
    let onlineMark = false;
    const nodes = el.querySelectorAll('span.boss-active-time, .boss-online-tag, .boss-online, .active-time, [class*="active-time"]');
    for (const n of nodes) {
      const t = ((n.innerText || n.textContent || '') + '').trim().replace(/\\s+/g, '');
      if (t) return t;
      const cls = (n.getAttribute && n.getAttribute('class')) || '';
      if (cls.includes('online')) onlineMark = true;
    }
    const info = el.querySelector('.boss-info, .job-card-footer, .card-footer, .job-info-footer');
    const roots = info ? [info, el] : [el];
    for (const root of roots) {
      const lines = ((root.innerText || '') + '').split(/\\n/).map(x => x.trim()).filter(Boolean);
      for (let i = lines.length - 1; i >= 0; i--) {
        const line = lines[i].replace(/\\s+/g, '');
        if (LINE.test(line)) return line;
      }
    }
    return onlineMark ? '在线' : '';
  };
  return Array.from(document.querySelectorAll('ul.rec-job-list li.job-card-box')).map(el => {
    const a = el.querySelector('a.job-name');
    const loc = el.querySelector('span.company-location');
    const name = el.querySelector('span.boss-name');
    return {
      job: (a && a.innerText ? a.innerText : '').trim(),
      company: (name && name.innerText ? name.innerText : '').trim(),
      area: (loc && loc.innerText ? loc.innerText : '').trim(),
      active: activeOf(el),
      href: (a && a.getAttribute('href')) ? a.getAttribute('href') : ''
    };
  });
}
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
    playwright = None
    context = None
    try:
        log.info(
            "筛选开始。详情上限 %s，onRisk=%s。配置 %s",
            "无" if settings.detail_limit < 0 else settings.detail_limit,
            "stop" if settings.stop_on_risk else "wait",
            settings.config_path,
        )
        playwright, context = open_chrome(settings.browser_data)
        page = fresh_page(context)
        Session(settings, page, stop).execute()
    except KeyboardInterrupt:
        log.info("收到停止")
    finally:
        if context is not None:
            context.close()
        if playwright is not None:
            playwright.stop()
        release(lock)
    log.info("筛选结束")


class Session:
    def __init__(self, settings: Settings, page, stop: threading.Event) -> None:
        self.settings = settings
        self.page = page
        self.stop = stop
        self.list_cards: dict[str, Card] = {}
        self.keyword_logs: dict[str, Path] = {}
        self.log: ScreenLog | None = None
        self.seen: dict[str, dict] = {}
        self.detail_reserved = 0
        self.empty_detail_streak = 0
        self.details_since_last_break = 0
        self.stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        page.on("response", self._on_response)

    def execute(self) -> None:
        self.seen = load_seen(self.settings.screen_dir, self.settings.keywords)
        codes = self.settings.city_codes
        for index, city_code in enumerate(codes):
            if self.stop.is_set():
                return
            self._city(city_code)
            if self.stop.is_set():
                return
            if index < len(codes) - 1:
                self._gap()

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
        self._open_log(keyword)
        url = base + ("&" if "?" in base else "?") + "query=" + urllib.parse.quote_plus(keyword)
        self._open_list(keyword, url)
        if self.stop.is_set():
            return
        harvested = self._scroll(keyword)
        if self.stop.is_set():
            return
        log.info("【%s】去重后 %s 条（列表接口 %s）", keyword, len(harvested), len(self.list_cards))
        self._triage(keyword, list(harvested.values()))

    def _open_log(self, keyword: str) -> None:
        self.list_cards.clear()
        existing = self.keyword_logs.get(keyword)
        if existing is not None:
            self.log = ScreenLog(existing)
            self.log.load()
            log.info("本词续写 %s", existing)
            return
        path = self.settings.screen_dir / screen_file_name(self.stamp, self.settings.job_type_name, keyword)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        self.keyword_logs[keyword] = path
        self.log = ScreenLog(path)
        log.info("本词筛选写入 %s", path)

    def _scroll(self, keyword: str) -> dict[str, Card]:
        harvested: dict[str, Card] = {}
        self._harvest(harvested)
        last = len(harvested)
        stable = 0
        stale = 0
        loaded = False
        for i in range(300):
            if self.stop.is_set() or self._halt("Boss 滚动列表时弹出人机验证或登录。"):
                return harvested
            try:
                self.page.evaluate("() => window.scrollBy(0, Math.floor(window.innerHeight * 1.5))")
                if self._sleep(2):
                    return harvested
                self._harvest(harvested)
                current = len(harvested)
                stable = stable + 1 if current == last else 0
                last = current
                log.info("【%s】滚动第%s轮，已收获%s条", keyword, i + 1, current)
                if stable >= 3:
                    self.page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
                    if self._sleep(2):
                        return harvested
                    self._harvest(harvested)
                    if len(harvested) > last:
                        stable = 0
                        last = len(harvested)
                footer = self._footer_visible()
                if i >= 5 and footer and stable >= 2:
                    loaded = True
                    break
                if i >= 5 and stable >= 8:
                    loaded = True
                    break
            except Exception as exc:
                if not _stale(exc):
                    raise
                stale += 1
                if stale > 20:
                    break
                self._sleep(1)
        if not loaded:
            log.warning("【%s】滚动到达 300 轮上限，按已加载的岗位继续", keyword)
        self._harvest(harvested)
        try:
            self.page.evaluate("window.scrollTo(0, 0);")
        except Exception:
            pass
        self._sleep(1)
        return harvested

    def _triage(self, keyword: str, cards: list[Card]) -> None:
        assert self.log is not None
        limit = self.settings.detail_limit
        remaining = 2**31 - 1 if limit < 0 else limit - self.detail_reserved
        need_ai: list[Card] = []
        direct: list[Card] = []
        retries: list[tuple[Card, dict]] = []
        for card in cards:
            if self.stop.is_set():
                return
            key = row_key(card.encrypt_id, card.company, card.job)
            city = classify_city(card.area)
            prior = self.seen.get(key)
            list_rule = rule_drop_reason(
                card.job, card.company, card.active, card.recruiter, "", **self.settings.rule_kwargs()
            )
            step = next_step(prior, city, list_rule, remaining)
            if step == "skip" or step == "leave":
                continue
            if step == "reclass":
                judged = with_stored_hr_drop(prior or {})
                stored_active = str((prior or {}).get("active") or "")
                ruled = card.with_active(stored_active) if stored_active else card
                self._write_card(keyword, ruled, "rule_drop", str(judged.get("reason") or ""), True)
                continue
            if step == "rule":
                self._write_card(
                    keyword, card, "rule_drop", rule_reason(list_rule), bool(list_rule and list_rule.startswith("HR未近3天"))
                )
                continue
            if step == "click":
                direct.append(card)
                remaining -= 1
                self.detail_reserved += 1
                continue
            if step == "jd" and prior is not None:
                retries.append((card, prior))
                continue
            need_ai.append(card)
        outcomes = self._title_ai(keyword, need_ai)
        worth: list[Card] = []
        for card, (action, reason) in zip(need_ai, outcomes, strict=True):
            if self.stop.is_set():
                return
            stage, labeled, click = title_disposition(action, reason, classify_city(card.area), remaining)
            self._write_card(keyword, card, stage, labeled, False)
            if click:
                worth.append(card)
                remaining -= 1
                self.detail_reserved += 1
        log.info("【%s】列表 %s 张，续点 %s 张，本词新点详情 %s 张", keyword, len(cards), len(direct), len(worth))
        self._retry_saved_jd(keyword, retries)
        self._details(keyword, direct + worth)

    def _retry_saved_jd(self, keyword: str, pairs: list[tuple[Card, dict]]) -> None:
        if not pairs:
            return
        log.info("JD重试 %s 张", len(pairs))

        def one(pair: tuple[Card, dict]) -> None:
            card, row = pair
            job = saved_jd_job(
                row,
                job=card.job,
                company=card.company,
                area=card.area,
                href=card.href,
                encrypt_id=card.encrypt_id,
            )
            self._screen_job(keyword, job, jd_retry_city(job), str(row.get("active") or ""))

        with ThreadPoolExecutor(max_workers=AI_PARALLELISM) as pool:
            futures = [pool.submit(one, pair) for pair in pairs]
            for future in futures:
                if self.stop.is_set():
                    break
                try:
                    future.result()
                except Exception as exc:
                    log.warning("JD重试失败: %s", exc)

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

    def _details(self, keyword: str, cards: list[Card]) -> None:
        if not cards:
            return
        try:
            self.page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' });")
            self._sleep(random.uniform(1.0, 1.8))
        except Exception:
            pass
        futures = []
        with ThreadPoolExecutor(max_workers=AI_PARALLELISM) as pool:
            for card in cards:
                if self.stop.is_set() or self._halt("Boss 弹出人机验证或登录页。"):
                    break
                if not card.encrypt_id:
                    log.warning("卡片没有岗位ID，保持待读 | %s | %s", card.company, card.job)
                    continue
                target = self._find_card(card.encrypt_id)
                if self.stop.is_set():
                    break
                if target is None:
                    log.warning("找不到岗位ID对应卡片，保持待读 | %s", card.encrypt_id)
                    continue
                try:
                    with self.page.expect_response(_is_detail, timeout=15_000) as waited:
                        self._human_click(target)
                    body = waited.value.text()
                except Exception:
                    if self._halt("Boss 点详情时弹出验证。"):
                        break
                    log.warning("等待岗位详情超时 | %s | %s", card.company, card.job)
                    continue
                self._pause_between_jobs()
                job = self._job_from_detail(card, body)
                if self.stop.is_set():
                    break
                if job is None:
                    continue
                city = classify_city(job["area"] or card.area)
                if city == "其它" and is_search_city(classify_city(card.area)):
                    city = classify_city(card.area)
                hr_text = job["active"] or card.active or ""
                if hr_text.strip() and not is_active_within_3_days(hr_text):
                    self._write_job(
                        keyword, job, city, "rule_drop", rule_reason("HR未近3天活跃：" + hr_text.strip()), hr_text, True
                    )
                    continue
                recruiter_rule = recruiter_drop_reason(
                    job["recruiterTitle"], job["recruiter"], self.settings.black_recruiters
                )
                if recruiter_rule:
                    self._write_job(keyword, job, city, "rule_drop", rule_reason(recruiter_rule), hr_text, False)
                    continue
                futures.append(pool.submit(self._screen_job, keyword, job, city, hr_text))
                if self._halt("Boss 弹出人机验证或登录页。"):
                    break
            for future in futures:
                try:
                    future.result()
                except Exception as exc:
                    log.warning("详情AI失败: %s", exc)

    def _human_click(self, target) -> None:
        try:
            box = target.bounding_box()
            if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                tx = box["x"] + random.uniform(box["width"] * 0.25, box["width"] * 0.75)
                ty = box["y"] + random.uniform(box["height"] * 0.25, box["height"] * 0.75)
                self.page.mouse.move(tx, ty, steps=random.randint(6, 12))
                target.hover(timeout=2000)
                self._sleep(random.uniform(0.3, 0.7))
        except Exception:
            pass
        target.click()

    def _job_from_detail(self, card: Card, body: str) -> dict | None:
        parsed = parse_detail(body)
        job_name = parsed.get("job") or ""
        company = parsed.get("company") or ""
        if not job_name.strip() and not company.strip():
            self.empty_detail_streak += 1
            log.warning("岗位详情为空 (%s/2)", self.empty_detail_streak)
            if self.empty_detail_streak >= 2 or needs_human(self.page):
                self._halt("Boss 读不到岗位详情，多半是人机验证或页面卡住。")
                self.empty_detail_streak = 0
            return None
        self.empty_detail_streak = 0
        href = self._detail_href() or card.href
        return {
            "job": job_name or card.job,
            "company": company or card.company,
            "salary": parsed.get("salary") or "",
            "area": parsed.get("area") or card.area,
            "recruiter": parsed.get("recruiter") or "",
            "recruiterTitle": parsed.get("recruiterTitle") or "",
            "active": parsed.get("active") or "",
            "href": href,
            "encryptId": extract_encrypt_id(href) or card.encrypt_id,
            "jd": parsed.get("jd") or "",
            "degree": parsed.get("degree") or "",
            "experience": parsed.get("experience") or "",
            "industry": parsed.get("industry") or "",
            "scale": parsed.get("scale") or "",
            "financing": parsed.get("financing") or "",
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

    def _screen_job(self, keyword: str, job: dict, city: str, hr_text: str) -> None:
        try:
            raw = complete(self.settings, jd_prompt(self.settings, keyword, job))
        except Exception as exc:
            log.warning("AI筛选失败 | %s | %s | %s", job["company"], job["job"], exc)
            self._write_job(keyword, job, city, "ai_jd_pending", ai_fail_reason("JD", str(exc)), hr_text, False)
            return
        keep = parse_keep(raw)
        reason = parse_reason(raw)
        if keep is None:
            self._write_job(keyword, job, city, "ai_jd_pending", ai_fail_reason("JD", reason), hr_text, False)
            return
        stage = "ai_keep" if keep else "ai_jd_drop"
        labeled = ai_jd_reason(reason)
        log.info("%s | %s | %s | %s", stage, job["company"], job["job"], labeled)
        self._write_job(keyword, job, city, stage, labeled, hr_text, False)

    def _write_job(
        self, keyword: str, job: dict, city: str, stage: str, reason: str, hr_text: str, hr_drop: bool
    ) -> None:
        jd = job.get("jd") or ""
        self._upsert(
            {
                "keyword": keyword,
                "company": job.get("company") or "",
                "job": job.get("job") or "",
                "salary": job.get("salary") or "",
                "area": job.get("area") or "",
                "recruiter": job.get("recruiter") or "",
                "active": hr_text or "",
                "href": job.get("href") or "",
                "encryptId": job.get("encryptId") or "",
                "jd": jd,
                "cityPage": city,
                "stage": stage,
                "reason": reason.strip() or "未写明",
                "hrDrop": hr_drop,
                "hasJd": bool(str(jd).strip()),
            }
        )

    def _pause_between_jobs(self) -> None:
        self.details_since_last_break += 1
        if self.details_since_last_break >= random.randint(6, 9):
            rest = random.randint(60, 100)
            log.info("拟真停歇：已连续查看 %s 份岗位，模拟休息 %s 秒...", self.details_since_last_break, rest)
            self.details_since_last_break = 0
            self._sleep(rest)
            return

        seconds = detail_gap_seconds(self.settings.wait_time)
        log.info("岗位间停顿 %s 秒", seconds)
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

    def _harvest(self, harvested: dict[str, Card]) -> None:
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
                job = str(item.get("job") or "").strip()
                company = str(item.get("company") or "").strip()
                if not job and not company and not encrypt_id:
                    continue
                active = str(item.get("active") or "").strip()
                if encrypt_id and not active:
                    listed = self.list_cards.get(encrypt_id)
                    if listed and listed.active:
                        active = listed.active
                key = row_key(encrypt_id, company, job)
                if not key:
                    continue
                nxt = Card(
                    job=job,
                    company=company,
                    area=str(item.get("area") or "").strip(),
                    active=active,
                    href=href,
                    encrypt_id=encrypt_id,
                )
                existing = harvested.get(key)
                if existing is not None:
                    if classify_city(existing.area) == "其它" and is_search_city(classify_city(nxt.area)):
                        harvested[key] = nxt
                    continue
                harvested[key] = nxt
        for extra in self.list_cards.values():
            key = row_key(extra.encrypt_id, extra.company, extra.job)
            if not key:
                continue
            existing = harvested.get(key)
            harvested[key] = extra if existing is None else overlay(existing, extra)

    def _write_card(self, keyword: str, card: Card, stage: str, reason: str, hr_drop: bool) -> None:
        self._upsert(
            {
                "keyword": keyword,
                "company": card.company,
                "job": card.job,
                "area": card.area,
                "active": card.active or "",
                "href": card.href,
                "encryptId": card.encrypt_id,
                "cityPage": classify_city(card.area),
                "stage": stage,
                "reason": reason.strip() or "未写明",
                "hrDrop": hr_drop,
                "hasJd": False,
            }
        )
        log.info("%s | %s | %s | %s", stage, card.company, card.job, reason)

    def _upsert(self, patch: dict) -> None:
        assert self.log is not None
        stored = self.log.upsert(patch)
        key = row_key(str(patch.get("encryptId") or ""), patch.get("company"), patch.get("job"))
        if stored is not None and key:
            self.seen[key] = stored

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
        self._sleep(2)

    def _find_card(self, encrypt_id: str):
        hit = self._card_locator(encrypt_id)
        if hit is not None:
            return hit
        try:
            for _ in range(30):
                if self._halt("Boss 找卡片时弹出人机验证或登录。"):
                    return None
                hit = self._card_locator(encrypt_id)
                if hit is not None:
                    return hit
                delta = random.randint(350, 600)
                self.page.mouse.wheel(0, delta)
                self._sleep(random.uniform(0.4, 0.7))

            self.page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' });")
            self._sleep(random.uniform(1.0, 1.5))
            for _ in range(30):
                if self._halt("Boss 找卡片时弹出人机验证或登录。"):
                    return None
                hit = self._card_locator(encrypt_id)
                if hit is not None:
                    return hit
                delta = random.randint(350, 600)
                self.page.mouse.wheel(0, delta)
                self._sleep(random.uniform(0.4, 0.7))
        except Exception as exc:
            log.debug("滚找卡片失败: %s", exc)
        return None

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
        log.info("词间冷却 %s 秒", self.settings.keyword_gap)
        self._sleep(self.settings.keyword_gap)

    def _sleep(self, seconds: float) -> bool:
        return sleep_until(self.stop, seconds)


def _parallel(label: str, cards: list[Card], fn, stop: threading.Event) -> list[tuple[str | None, str]]:
    log.info("%s 并行 %s 张", label, len(cards))
    out: list[tuple[str | None, str]] = [(None, label + "未返回")] * len(cards)
    with ThreadPoolExecutor(max_workers=AI_PARALLELISM) as pool:
        futures = [pool.submit(fn, card) for card in cards]
        for index, future in enumerate(futures):
            if stop.is_set():
                break
            try:
                out[index] = future.result()
            except Exception as exc:
                out[index] = (None, str(exc))
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
