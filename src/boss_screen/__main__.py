"""从仓库根启动筛选：uv run python src/boss_screen/__main__.py"""

from __future__ import annotations

import sys
from pathlib import Path


def _prepare_path() -> None:
    src = Path(__file__).resolve().parents[1]
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


if __name__ == "__main__":
    _prepare_path()
    if sys.argv[1:]:
        raise SystemExit("未知参数")
    from boss_screen.run import main

    main()
