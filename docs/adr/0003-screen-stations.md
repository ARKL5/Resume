# 停驻记在 stage，待点记在停因里

jsonl 用 `stage` 和 `cityPage`，不另写 `column`、`status`、`keep`；缺其中任一的行，加载和对照页都跳过，不映射旧键。待点和含糊都是 `jd_wait`：停因含「将点详情」或「详情上限」为待点，其余为含糊。`jd_wait_other` 在城市分页「其它」，该页待读不再分分类。规则按停因分组，点进分类后直接列岗。列表标签只送给标题 AI，不写入 jsonl。取舍文案在 `boss.yaml` 的提示词里。

**Code**: `src/boss_screen/rules.py`、`screen/src/types.ts`

**Considered Options**: 给待点单独的 stage 或字段；加载时映射旧键。
