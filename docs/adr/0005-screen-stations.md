# 四处停驻与 jsonl 字段

对照页四处停驻：规则 / AI / 待读 / 保留。jsonl 用 `stage` 记一岗停在哪一步（`rule_drop`、`ai_title_drop` / `ai_title_pending`、`jd_wait` / `jd_wait_other`、`ai_jd_drop` / `ai_jd_pending`、`ai_keep`），用 `cityPage` 分页。停因 `规则 …` / `AI 标题 …` / `AI JD …`，写清为什么停在这（含糊待读、本可点但本轮详情上限、其它城市不点）。不写 `column` / `status` / `keep`，不加新字段。岗位/公司字面和标题/JD 提示词在 `boss/boss.yaml`（`rules` / `prompts`）；「训练」不含「后训练」仍是规则。标题 AI 短偏好三态；产品经理/产品+Agent 无开发或工程师 → 待读不点。收获不写中间态。加载与对照页都跳过没有合法 `stage`/`cityPage` 的行，不映射旧键。

**Code**: `boss/src/main/java/com/getjobs/worker/boss/Boss.java`、`screen/`、`boss/boss.yaml` 的 `screenResults`

**Considered Options**: 磁盘仍用旧键；加载时映射旧键。
