# Project

个人求职投递件与投递进度维护。

## Required reading

**Engineering standards**（改代码或设计之前，以及审查时）：[`docs/agents/engineering-standards.md`](docs/agents/engineering-standards.md)

**Glossary**（用到或改领域词时）：[`CONTEXT.md`](CONTEXT.md)

**ADRs**（动到哪一块，就读那一块）：[`docs/adr/`](docs/adr/)

## Verification

投递件：`uv run .agents/skills/qiaomu-campus-resume/scripts/validate_resume.py resume/resume-data-agent.json`，校招件把路径换成 `resume/resume-data-campus.json`。只查 JSON 结构，不含 PDF。声称渲染完成时再按渲染 skill 出 PDF。

对照页：`cd screen && npm test && npm run build`。测试覆盖数据脚本，构建覆盖类型检查与打包。

筛选运行时：`uv run --group dev ruff check src tests`，`uv run --group dev pyright`，`uv run --group dev pytest`。

筛选进程从仓库根一直跑到自己结束：`uv run python src/boss_screen/__main__.py`。这不是校验。
