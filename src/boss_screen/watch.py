"""后台拉起筛选并阻塞值守日志：平时静默输出里程碑，遇到风控暂停、停机异常、卡死或跑完时立即返回。"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from boss_screen.config import REPO_ROOT, load_settings
from boss_screen.proc_lock import default_lock_path, running_pid

MILESTONE_MARKERS = (
    "流式筛选开始",
    "库内残留待评 JD",
    "收获新卡片",
    "ai_keep |",
    "已连续遇到",
    "列表已到底部",
    "提前结束该词",
    "汇总：",
    "拟真长休",
    "词间冷却",
    "验证已消失，继续",
    "收到停止",
    "筛选结束",
)

ALERT_MARKERS = (
    "暂停等人",
    "风控，停止",
    "读不到页面，停止",
    "停止本轮筛选",
    " ERROR ",
)


def main() -> int:
    settings = load_settings()
    if settings.log_file is None:
        raise SystemExit("watch 需要 boss.yaml 配置 logFile")
    log_file = settings.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if not log_file.exists():
        log_file.touch()

    lock_path = default_lock_path()
    pid = running_pid(lock_path)
    offset = log_file.stat().st_size
    if pid is None:
        pid = _spawn_detached(lock_path)
        print(f"已后台拉起筛选进程 PID={pid}，日志 {log_file}", flush=True)
    else:
        print(f"已挂接运行中筛选进程 PID={pid}，日志 {log_file}", flush=True)

    return watch_log(log_file, lambda: running_pid(lock_path) is not None, offset=offset)


def _spawn_detached(lock_path: Path, wait_seconds: float = 5.0) -> int:
    entry = Path(__file__).with_name("__main__.py").resolve()
    proc = subprocess.Popen(
        [sys.executable, str(entry)],
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        pid = running_pid(lock_path)
        if pid is not None:
            return pid
        if proc.poll() is not None:
            raise SystemExit(f"筛选进程启动后立即退出（code={proc.returncode}）")
        time.sleep(0.05)
    return proc.pid


def watch_log(
    log_file: Path,
    is_alive: Callable[[], bool],
    *,
    offset: int = 0,
    poll_seconds: float = 1.0,
    stall_seconds: float = 300.0,
    out: TextIO = sys.stdout,
) -> int:
    pending = ""
    last_activity = time.monotonic()

    while True:
        offset, pending, lines = _read_new_lines(log_file, offset, pending)
        if lines:
            last_activity = time.monotonic()
            for line in lines:
                if _matches(line, ALERT_MARKERS):
                    print(line, file=out, flush=True)
                    return 2
                if _matches(line, MILESTONE_MARKERS):
                    print(line, file=out, flush=True)

        if not is_alive():
            offset, pending, tail_lines = _read_new_lines(log_file, offset, pending, flush_partial=True)
            for line in tail_lines:
                if _matches(line, ALERT_MARKERS):
                    print(line, file=out, flush=True)
                    return 2
                if _matches(line, MILESTONE_MARKERS):
                    print(line, file=out, flush=True)
            print("值守结束：筛选进程已退出", file=out, flush=True)
            return 0

        if time.monotonic() - last_activity >= stall_seconds:
            print(f"值守告警：日志已连续 {int(stall_seconds)} 秒无更新，请检查 9222 浏览器页面", file=out, flush=True)
            return 2

        time.sleep(poll_seconds)


def _read_new_lines(
    log_file: Path,
    offset: int,
    pending: str,
    *,
    flush_partial: bool = False,
) -> tuple[int, str, list[str]]:
    if not log_file.is_file():
        return offset, pending, []
    try:
        with open(log_file, "rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
    except OSError:
        return offset, pending, []
    if not chunk and not (flush_partial and pending):
        return offset, pending, []
    offset += len(chunk)
    text = pending + chunk.decode("utf-8", errors="replace")
    parts = text.splitlines(keepends=True)
    lines: list[str] = []
    remainder = ""
    for part in parts:
        if part.endswith(("\n", "\r")) or flush_partial:
            lines.append(part.rstrip("\r\n"))
        else:
            remainder = part
    return offset, remainder, lines


def _matches(line: str, markers: tuple[str, ...]) -> bool:
    return any(marker in line for marker in markers)
