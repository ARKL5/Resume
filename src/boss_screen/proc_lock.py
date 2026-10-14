"""单实例进程锁，防止同时启动多个筛选进程争抢同一浏览器目录。"""

from __future__ import annotations

import fcntl
import logging
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
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def take_lock(path: Path | None = None):
    chosen = path or default_lock_path()
    handle = acquire(chosen)
    if handle is None:
        log.error("已有筛选进程在运行")
        raise SystemExit(1)
    return handle


def release(handle) -> None:
    if handle is None:
        return
    try:
        handle.seek(0)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    handle.close()
