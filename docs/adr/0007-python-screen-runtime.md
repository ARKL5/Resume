# 筛选运行时改为仓库根的 Python 长驻命令

个人工具的筛选运行时放在仓库根 `src/`，依赖写在根 `pyproject.toml`。一个长驻命令跑筛选：Patchright 拉起本机有界面 Chrome（持久用户目录、不注入 stealth），读配置、追加 jsonl、日志打在终端。不提供 HTTP。筛选口径、停驻、jsonl 字段、送进模型的字段保持 ADR 0001、0004、0005。代聊是单独命令，见 ADR 0009。`boss/` 在代聊迁完后整份删除。配置、登录目录和结果目录都在仓库根，路径相对 `boss.yaml`。`src/` 只放代码。

**Code**: `src/boss_screen/`、`boss.yaml`

**Considered Options**: 薄 HTTP 保住对照页现有路径；在 `boss/` 里单开一个 uv 项目；把登录目录和旧 jsonl 复制进 `src/`；筛选一跑通就删 Java。

**Consequences**: 对照页读 yaml，见 ADR 0009。`boss/` 已删除。正式开跑前的结果目录见 ADR 0008。
