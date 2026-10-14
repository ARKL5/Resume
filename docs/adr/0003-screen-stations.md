# 状态由 stage 独立表达，不向 reason 拼接标记

数据库与前后端统一用独立的 `stage` 值（`rule_drop`、`ai_title_drop`、`ai_title_pending`、`jd_park`、`jd_queued`、`ai_jd_pending`、`ai_jd_drop`、`ai_keep`）表达停驻与分类，不再向 `reason` 拼接阶段前缀或待点后缀，避免靠正则拆解评语反推状态。
