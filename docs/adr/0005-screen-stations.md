# 四处停驻与 jsonl 字段

对照页四处停驻：规则 / AI / 待读 / 保留。jsonl 用 `stage` 记一岗停在哪一步（`rule_drop`、`ai_title_drop` / `ai_title_pending`、`jd_wait` / `jd_wait_other`、`ai_jd_drop` / `ai_jd_pending`、`ai_keep`），用 `cityPage` 分页。停因 `规则 …` / `AI 标题 …` / `AI JD …`，写清为什么停在这（含糊待读、本可点但本轮详情上限、其它城市不点）。不写 `column` / `status` / `keep`，不加新字段。规则、保留没有分类。AI、待读下方单独一行是分类，须点过才出列表：标题淘汰 `ai_title_drop`、JD淘汰 `ai_jd_drop`、标题失败 `ai_title_pending`、JD失败 `ai_jd_pending`；待点（`jd_wait` 且停因含「将点详情」或「详情上限」）、含糊（其余 `jd_wait`）。点进分类后直接列岗，停因整句写在行内，不再当组头。将点、详情上限、其它城不点跟在停因后面，不拆字段、不加样式。规则仍按停因分组。`jd_wait_other` 走城市分页「其它」，待读在该页不再分分类。岗位/公司字面和标题/JD 提示词在 `boss.yaml`（`rules` / `prompts`）；「训练」不含「后训练」仍是规则。标题 AI 短偏好三态，可看列表标签，标签不写 jsonl。JD AI 同一套偏好、二元 keep 切开保留/JD淘汰，停因写 3～4 句（方向与职责、公司事实、项目匹配、擦边风险），不超过 200 字，不加 jsonl 字段。详情品牌块抽出行业/规模/融资、学历要求、经验要求只填进提示词；jsonl 的 `area` 只留地点。招聘者头衔规则停因 `招聘者含：…`。产品经理/产品+Agent 无开发或工程师 → 待读含糊、不点。收获不写中间态。加载与对照页都跳过没有合法 `stage`/`cityPage` 的行，不映射旧键。

**Code**: `src/boss_screen/`、`screen/`、`boss.yaml` 的 `screenResultsDir`

**Considered Options**: 磁盘仍用旧键；加载时映射旧键。
