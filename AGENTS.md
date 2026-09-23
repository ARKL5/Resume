# Project

个人求职投递件与投递进度维护。

## Required reading

**工程标准**（改代码/设计之前、审查时）：[`docs/agents/engineering-standards.md`](docs/agents/engineering-standards.md)

**领域词**（用词、新名）：[`CONTEXT.md`](CONTEXT.md)

**决策**（开聊、Boss 筛选、对照页之前）：[`docs/adr/`](docs/adr/)

## Verification

投递件：`bash scripts/verify.sh`。声称渲染完成时再按渲染 skill 出 PDF。

对照页：`cd screen; npm run build`。看页面 `npm run dev`。

筛选运行时：`uv run --group dev pytest`。启动（仓库根、长驻，不要用短超时当前台杀掉）：`uv run python src/boss_screen/__main__.py`。代聊（当场点名；筛选还在跑会拒绝）：`uv run python src/boss_screen/__main__.py chat <encryptId> [--image]`。
