"""后台启动与日志值守；退出码 0 必须有本轮完成证明。"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from boss_screen.config import REPO_ROOT, load_settings
from boss_screen.proc_lock import default_lock_path, running_pid

MILESTONE_MARKERS = (
    "流式筛选开始", "库内残留待评 JD", "收获新卡片", "ai_keep |", "已连续遇到",
    "列表接口确认结束", "滚动预算", "汇总：", "拟真长休", "词间冷却",
    "目标业务已恢复，继续", "筛选结果：",
)
ALERT_MARKERS = ("暂停等人", "停止本轮筛选", " ERROR ", "Traceback (most recent call last)")


def main(*, start: bool = False) -> int:
    settings = load_settings()
    if settings.log_file is None:
        raise SystemExit("watch 需要 boss.yaml 配置 logFile")
    log_file = settings.log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.touch(exist_ok=True)
    lock_path = default_lock_path()
    pid = running_pid(lock_path)
    offset, has_run = _last_run(log_file)
    if pid is None and (start or not has_run):
        offset = log_file.stat().st_size
        pid = _spawn_detached(lock_path, log_file)
        print(f"已后台拉起筛选进程 PID={pid}，日志 {log_file}", flush=True)
    elif pid is not None:
        print(f"已续守筛选进程 PID={pid}，回看本轮日志 {log_file}", flush=True)
    else:
        print("筛选进程已退出，报告上轮结果；新一轮请使用 --watch --start", flush=True)
    return watch_log(log_file, lambda: running_pid(lock_path) == pid and pid is not None, offset=offset)


def _last_run(log_file: Path) -> tuple[int, bool]:
    offset = 0
    found = False
    with log_file.open("rb") as handle:
        while True:
            position = handle.tell()
            line = handle.readline()
            if not line:
                break
            if "流式筛选开始".encode() in line:
                offset, found = position, True
    return offset, found


def _spawn_detached(lock_path: Path, log_file: Path, wait_seconds: float = 5.0) -> int:
    entry = Path(__file__).with_name("__main__.py").resolve()
    # 正常日志由 FileHandler 写；stderr 同步保留启动错误与 traceback。
    with log_file.open("ab") as errors:
        proc = subprocess.Popen(
            [sys.executable, str(entry)], cwd=str(REPO_ROOT), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=errors, start_new_session=True,
            env={**os.environ, "BOSS_SCREEN_FILE_ONLY": "1"},
        )
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        pid = running_pid(lock_path)
        if pid is not None and pid == proc.pid:
            return pid
        if proc.poll() is not None:
            raise SystemExit(f"筛选启动后退出（code={proc.returncode}），检查 {log_file}")
        time.sleep(0.05)
    raise SystemExit(f"筛选启动未取得进程锁，检查 {log_file}，PID={proc.pid}")


def watch_log(
    log_file: Path, is_alive: Callable[[], bool], *, offset: int = 0,
    poll_seconds: float = 1.0, stall_seconds: float = 300.0, out: TextIO = sys.stdout,
) -> int:
    pending = ""
    last_activity = time.monotonic()
    alert = ""
    result = ""
    while True:
        alive = is_alive()
        offset, pending, lines = _read_new_lines(log_file, offset, pending, flush_partial=not alive)
        if lines:
            last_activity = time.monotonic()
            for line in lines:
                if "流式筛选开始" in line:
                    alert = result = ""
                if "目标业务已恢复，继续" in line:
                    alert = ""
                if _matches(line, ALERT_MARKERS):
                    alert = line
                if "筛选结果：" in line:
                    result = line.rsplit("筛选结果：", 1)[1].strip()
                if _matches(line, MILESTONE_MARKERS):
                    print(line, file=out, flush=True)
        if not alive:
            if alert:
                print(alert, file=out, flush=True)
            print(f"值守结束：{result or '异常（缺少本轮结束结果）'}", file=out, flush=True)
            return 0 if result == "完成" and not alert else 2
        if alert:
            print(alert, file=out, flush=True)
            return 2
        if time.monotonic() - last_activity >= stall_seconds:
            print(f"值守告警：日志已连续 {int(stall_seconds)} 秒无更新，请人工检查原 Chrome", file=out, flush=True)
            return 2
        time.sleep(poll_seconds)


def _read_new_lines(
    log_file: Path, offset: int, pending: str, *, flush_partial: bool = False,
) -> tuple[int, str, list[str]]:
    if not log_file.is_file():
        return offset, pending, []
    try:
        with log_file.open("rb") as handle:
            if handle.seek(0, 2) < offset:
                offset, pending = 0, ""
            handle.seek(offset)
            chunk = handle.read()
    except OSError:
        return offset, pending, []
    offset += len(chunk)
    parts = (pending + chunk.decode("utf-8", errors="replace")).splitlines(keepends=True)
    lines = []
    remainder = ""
    for part in parts:
        if part.endswith(("\n", "\r")) or flush_partial:
            lines.append(part.rstrip("\r\n"))
        else:
            remainder = part
    return offset, remainder, lines


def _matches(line: str, markers: tuple[str, ...]) -> bool:
    return any(marker in line for marker in markers)
