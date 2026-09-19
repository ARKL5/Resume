# 四处停驻与 jsonl 字段

对照页四处停驻：规则 / AI / 待读 / 保留。jsonl 用 `stage` 记一岗停在哪一步（`rule_drop`、`ai_title_drop` / `ai_title_pending`、`jd_wait` / `jd_wait_other`、`ai_jd_drop` / `ai_jd_pending`、`ai_keep`），用 `cityPage` 分页。停因 `规则 …` / `AI 标题 …` / `AI JD …`。不写 `column` / `status` / `keep`。岗位名字面（训练不含后训练）见 `JOB_TITLE_DROP`。标题 AI 短偏好，JD AI 全文；产品+Agent/AI/开发过标题。收获不写中间态。加载与对照页都跳过没有合法 `stage`/`cityPage` 的行，不映射旧键。

**Code**: `D:\38993\Documents\get_jobs\src\main\java\com\getjobs\worker\boss\Boss.java`、本仓 `screen/`、`screen-results.jsonl`

**Considered Options**: 磁盘仍用旧键；加载时映射旧键。
