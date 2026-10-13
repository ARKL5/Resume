# 筛选是仓库根的一条 Python 命令

运行时在 `src/boss_screen/`，依赖在根 `pyproject.toml`。一条长驻命令拉起本机有界面的 Chrome（持久登录目录），读 `boss.yaml`，追加 jsonl，日志打在终端，不提供 HTTP。配置、登录目录、结果目录都在仓库根，路径相对 `boss.yaml`；`src/` 只放代码。`waitTime` 低于 18 秒时仍按 18 秒。

**Code**: `src/boss_screen/`、`pyproject.toml`

**Considered Options**: 用只读 HTTP 给对照页供数；把运行时放回已删的 Java 工程。
