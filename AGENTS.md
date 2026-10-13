# Project

Boss 岗位筛选与代聊，外加只读对照页。

## Required reading

**Glossary**（用到或改领域词时）：[`CONTEXT.md`](CONTEXT.md)

**ADRs**（动到哪一块，就读哪一块）：[`docs/adr/`](docs/adr/)

## Standards

- **Follow the surroundings.** Follow project conventions and explain necessary departures.
- **Complete the task.** Deliver the requested behaviour and relevant failure paths.
- **Replace outright.** A change leaves one way to do the thing. Callers and tests move with that way.
- **Test behaviour.** Derive assertions from requirements, contracts, or defects. For fixes, show the regression fails on the bug where practical. Name tests by scenario and expected result.
- **Automate deterministic rules.** Use lint, types, and tests. Keep their configuration in tools, not in this file.
- **Boundary.** The screening runtime lives at the repo root in `src/boss_screen/`. The workbench only changes `screen/`, and reads the repo-root `boss.yaml` itself. This repo screens Boss postings and chats on demand; not a hiring platform, not a business backend.
- **Personal tool.** Do not publish. Prefer one less choice, mode, or field. The owner being able to read and change it beats foolproofing and automatic tracking.

## Verification

对照页：`cd screen && pnpm test && pnpm run build`。测试覆盖数据脚本，构建覆盖类型检查与打包。

筛选运行时：`uv run --group dev ruff check src tests`，`uv run --group dev pyright`，`uv run --group dev pytest`。

筛选进程从仓库根一直跑到自己结束：`uv run python src/boss_screen/__main__.py`。这不是校验。
