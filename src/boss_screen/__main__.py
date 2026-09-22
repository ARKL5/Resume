"""从仓库根启动。

筛选：uv run python src/boss_screen/__main__.py
代聊：uv run python src/boss_screen/__main__.py chat <encryptId> [--image]
"""

from __future__ import annotations

import sys
from pathlib import Path


def _prepare_path() -> None:
    src = Path(__file__).resolve().parents[1]
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


if __name__ == "__main__":
    _prepare_path()
    args = sys.argv[1:]
    if args[:1] == ["chat"]:
        from boss_screen.chat import main as chat_main

        chat_main(args[1:])
    elif args:
        raise SystemExit("未知命令")
    else:
        from boss_screen.run import main

        main()
