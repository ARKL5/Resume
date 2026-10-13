"""已开聊。一行一份 JSON，按 encryptId 去重。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def load_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        row = json.loads(text)
        found.add(row["encryptId"])
    return found


def append_opened(path: Path, encrypt_id: str) -> None:
    if not encrypt_id.strip():
        return
    row = {
        "encryptId": encrypt_id,
        "at": datetime.now(UTC).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
