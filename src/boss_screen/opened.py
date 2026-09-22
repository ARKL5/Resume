"""已开聊。一行一个 encryptId。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("{"):
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            encrypt_id = str(row.get("encryptId") or "").strip()
            if encrypt_id:
                found.add(encrypt_id)
            continue
        found.add(text)
    return found


def append_opened(path: Path, encrypt_id: str, company: str = "", job: str = "") -> None:
    if not encrypt_id.strip():
        return
    row = {
        "encryptId": encrypt_id,
        "company": company,
        "job": job,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
