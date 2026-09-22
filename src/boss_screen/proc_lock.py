"""筛选和代聊不能同时持有同一登录目录。"""

from __future__ import annotations

import logging
import msvcrt
from pathlib import Path

from boss_screen.config import REPO_ROOT

log = logging.getLogger("boss_screen")


def default_lock_path() -> Path:
    return REPO_ROOT / ".boss-screen.lock"


def acquire(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+b")
    try:
        if handle.seek(0, 2) < 1:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def take_lock(path: Path | None = None):
    chosen = path or default_lock_path()
    handle = acquire(chosen)
    if handle is None:
        log.error("已有筛选或代聊在跑")
        raise SystemExit(1)
    return handle


def release(handle) -> None:
    if handle is None:
        return
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    handle.close()
