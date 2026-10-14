"""SQLite 持久化岗位库（WAL 模式，支持流式写入与对照页并发读取）。"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from boss_screen.rules import is_placed_row, is_search_city, valid_encrypt_id

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    encrypt_id TEXT PRIMARY KEY,
    company TEXT NOT NULL DEFAULT '',
    job TEXT NOT NULL DEFAULT '',
    salary TEXT NOT NULL DEFAULT '',
    area TEXT NOT NULL DEFAULT '',
    city_page TEXT NOT NULL DEFAULT '其它',
    recruiter TEXT NOT NULL DEFAULT '',
    recruiter_title TEXT NOT NULL DEFAULT '',
    active TEXT NOT NULL DEFAULT '',
    href TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    jd TEXT NOT NULL DEFAULT '',
    degree TEXT NOT NULL DEFAULT '',
    experience TEXT NOT NULL DEFAULT '',
    industry TEXT NOT NULL DEFAULT '',
    scale TEXT NOT NULL DEFAULT '',
    financing TEXT NOT NULL DEFAULT '',
    keyword TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '[]',
    stage TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_stage ON jobs(stage);
"""

_TEXT_FIELDS = (
    "company",
    "job",
    "salary",
    "area",
    "recruiter",
    "recruiterTitle",
    "active",
    "href",
    "tags",
    "jd",
    "degree",
    "experience",
    "industry",
    "scale",
    "financing",
)


class JobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._conn.execute("PRAGMA busy_timeout=5000;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def get(self, encrypt_id: str) -> dict | None:
        if not valid_encrypt_id(encrypt_id):
            return None
        with self._lock:
            cur = self._conn.execute("SELECT * FROM jobs WHERE encrypt_id = ?", (encrypt_id.strip(),))
            row = cur.fetchone()
            return _row_to_dict(row) if row is not None else None

    def pending_jd_rows(self) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM jobs WHERE stage IN ('ai_jd_pending', 'jd_queued') AND trim(jd) != '' ORDER BY updated_at ASC"
            )
            return [_row_to_dict(r) for r in cur.fetchall()]

    def upsert(self, patch: dict) -> dict | None:
        raw_id = str(patch.get("encryptId") or patch.get("encrypt_id") or "").strip()
        if not valid_encrypt_id(raw_id):
            return None
        with self._lock:
            cur = self._conn.execute("SELECT * FROM jobs WHERE encrypt_id = ?", (raw_id,))
            existing_row = cur.fetchone()
            existing = _row_to_dict(existing_row) if existing_row is not None else {}

            now = datetime.now(UTC).isoformat()
            merged: dict = {
                "encryptId": raw_id,
                "firstSeenAt": existing.get("firstSeenAt") or now,
                "updatedAt": now,
            }

            for camel in _TEXT_FIELDS:
                incoming = str(patch.get(camel) or "").strip()
                prior = str(existing.get(camel) or "").strip()
                if camel == "area" and prior and not is_search_city( str(patch.get("cityPage") or "")) and is_search_city(str(existing.get("cityPage") or "")):
                    merged[camel] = prior
                else:
                    merged[camel] = incoming or prior

            incoming_city = str(patch.get("cityPage") or "").strip()
            prior_city = str(existing.get("cityPage") or "").strip()
            if incoming_city == "其它" and is_search_city(prior_city):
                merged["cityPage"] = prior_city
            else:
                merged["cityPage"] = incoming_city or prior_city or "其它"

            keywords = list(existing.get("keywords") or [])
            for extra_kw in patch.get("keywords") or []:
                kw_text = str(extra_kw or "").strip()
                if kw_text and kw_text not in keywords:
                    keywords.append(kw_text)
            kw = str(patch.get("keyword") or "").strip()
            if kw and kw not in keywords:
                keywords.append(kw)
            merged["keyword"] = kw or str(existing.get("keyword") or "")
            merged["keywords"] = keywords

            stage = str(patch.get("stage") or existing.get("stage") or "").strip()
            reason = str(patch.get("reason") if "reason" in patch else (existing.get("reason") or "")).strip()
            merged["stage"] = stage
            merged["reason"] = reason or "未写明"

            if not is_placed_row(merged):
                return None

            self._conn.execute(
                """
                INSERT INTO jobs (
                    encrypt_id, company, job, salary, area, city_page,
                    recruiter, recruiter_title, active, href, tags, jd,
                    degree, experience, industry, scale, financing,
                    keyword, keywords, stage, reason, first_seen_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(encrypt_id) DO UPDATE SET
                    company = excluded.company,
                    job = excluded.job,
                    salary = excluded.salary,
                    area = excluded.area,
                    city_page = excluded.city_page,
                    recruiter = excluded.recruiter,
                    recruiter_title = excluded.recruiter_title,
                    active = excluded.active,
                    href = excluded.href,
                    tags = excluded.tags,
                    jd = excluded.jd,
                    degree = excluded.degree,
                    experience = excluded.experience,
                    industry = excluded.industry,
                    scale = excluded.scale,
                    financing = excluded.financing,
                    keyword = excluded.keyword,
                    keywords = excluded.keywords,
                    stage = excluded.stage,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (
                    merged["encryptId"],
                    merged["company"],
                    merged["job"],
                    merged["salary"],
                    merged["area"],
                    merged["cityPage"],
                    merged["recruiter"],
                    merged["recruiterTitle"],
                    merged["active"],
                    merged["href"],
                    merged["tags"],
                    merged["jd"],
                    merged["degree"],
                    merged["experience"],
                    merged["industry"],
                    merged["scale"],
                    merged["financing"],
                    merged["keyword"],
                    json.dumps(merged["keywords"], ensure_ascii=False),
                    merged["stage"],
                    merged["reason"],
                    merged["firstSeenAt"],
                    merged["updatedAt"],
                ),
            )
            self._conn.commit()
            return merged


def _row_to_dict(row: sqlite3.Row) -> dict:
    try:
        raw_keywords = json.loads(row["keywords"] or "[]")
        keywords = [str(k).strip() for k in raw_keywords if str(k).strip()] if isinstance(raw_keywords, list) else []
    except json.JSONDecodeError:
        keywords = []
    return {
        "encryptId": row["encrypt_id"],
        "company": row["company"],
        "job": row["job"],
        "salary": row["salary"],
        "area": row["area"],
        "cityPage": row["city_page"],
        "recruiter": row["recruiter"],
        "recruiterTitle": row["recruiter_title"],
        "active": row["active"],
        "href": row["href"],
        "tags": row["tags"],
        "jd": row["jd"],
        "degree": row["degree"],
        "experience": row["experience"],
        "industry": row["industry"],
        "scale": row["scale"],
        "financing": row["financing"],
        "keyword": row["keyword"],
        "keywords": keywords,
        "stage": row["stage"],
        "reason": row["reason"],
        "firstSeenAt": row["first_seen_at"],
        "updatedAt": row["updated_at"],
    }
