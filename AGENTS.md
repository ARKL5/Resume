# Project

个人求职投递件与投递进度维护。命令用 PowerShell 7（`pwsh`）。Python 用仓库 `uv`。git 只在本机 commit。

## Required reading

**工程标准**（改代码/设计之前、审查时）：[`docs/agents/engineering-standards.md`](docs/agents/engineering-standards.md)

**领域词**（用词、新名）：[`CONTEXT.md`](CONTEXT.md)

**决策**（开聊、Boss 筛选、对照页之前）：[`docs/adr/`](docs/adr/)

**渲染**（改投递件、重渲染、或声称投递件完成时）：[`.agents/skills/qiaomu-campus-resume/SKILL.md`](.agents/skills/qiaomu-campus-resume/SKILL.md)

**对照页实现**（改 `screen/` 之前）：[`.agents/skills/frontend-design/SKILL.md`](.agents/skills/frontend-design/SKILL.md) 与 [`.agents/skills/vercel-react-best-practices/SKILL.md`](.agents/skills/vercel-react-best-practices/SKILL.md)

## Verification

投递件：`pwsh -File scripts/verify.ps1`。声称渲染完成时再按渲染 skill 出 PDF。

对照页：`cd screen; npm run build`。看页面 `npm run dev`。

筛选运行时：`uv run --group dev pytest`。启动（仓库根、长驻，不要用短超时当前台杀掉）：`uv run python src/boss_screen/__main__.py`。代聊（当场点名；筛选还在跑会拒绝）：`uv run python src/boss_screen/__main__.py chat <encryptId> [--image]`。
