"""一份筛选结果 jsonl，以及当前目录里的已筛。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from boss_screen.rules import is_placed_row, row_key, slug


class ScreenLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.rows: dict[str, dict] = {}
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            self.rows.clear()
            for row in read_rows(self.path):
                key = row_key(str(row.get("encryptId") or ""), row.get("company"), row.get("job"))
                if key:
                    self.rows[key] = row

    def upsert(self, patch: dict) -> dict | None:
        with self._lock:
            return self._upsert(patch)

    def _upsert(self, patch: dict) -> dict | None:
        key = row_key(str(patch.get("encryptId") or ""), patch.get("company"), patch.get("job"))
        if not key:
            return None
        row = self.rows.get(key)
        if row is None and key.startswith("id:"):
            name_key = row_key("", patch.get("company"), patch.get("job"))
            if name_key:
                row = self.rows.pop(name_key, None)
        if row is None:
            row = {}
        row.update(patch)
        _strip_dead(row)
        keywords = list(row.get("keywords") or [])
        kw = str(patch.get("keyword") or "")
        if kw and kw not in keywords:
            keywords.append(kw)
        row["keywords"] = keywords
        self.rows[key] = row
        self._persist()
        return dict(row)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in self.rows.values()]
        text = ("\n".join(lines) + "\n") if lines else ""
        self.path.write_text(text, encoding="utf-8")


def load_seen(directory: Path, keywords: list[str]) -> dict[str, dict]:
    """当前结果目录的已筛。同一岗位取文件名时间戳最新的一行；同一轮按写完时间，后写完的盖过先写完的。"""
    if not directory.exists():
        return {}
    order = {slug(keyword): index for index, keyword in enumerate(keywords)}
    files = [path for path in directory.glob("*.jsonl") if path.is_file()]
    files.sort(key=lambda path: _seen_rank(path, order))
    seen: dict[str, dict] = {}
    for path in files:
        for row in read_rows(path):
            key = row_key(str(row.get("encryptId") or ""), row.get("company"), row.get("job"))
            if key:
                seen[key] = row
    return seen


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or not is_placed_row(row):
            continue
        _strip_dead(row)
        rows.append(row)
    return rows


def _seen_rank(path: Path, order: dict[str, int]) -> tuple[str, int, int, str]:
    stamp, keyword_slug = _split_screen_name(path.stem)
    try:
        written = path.stat().st_mtime_ns
    except OSError:
        written = 0
    return stamp, written, order.get(keyword_slug, 10_000), path.name


def _split_screen_name(stem: str) -> tuple[str, str]:
    parts = stem.split("_", 2)
    if len(parts) < 3:
        return stem, ""
    return parts[0], parts[2]


def _strip_dead(row: dict) -> None:
    row.pop("column", None)
    row.pop("status", None)
    row.pop("keep", None)
