# 筛选是仓库根的一条 Python 命令

运行时在 `src/boss_screen/`，依赖在根 `pyproject.toml`。一条长驻命令拉起本机有界面的 Chrome（持久登录目录），读 `boss.yaml`，流式写入 SQLite，不提供 HTTP。`waitTime` 低于 18 秒时仍按 18 秒保底。
