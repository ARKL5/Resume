# 列表上筛选，城市只分页

字面、黑名单和招聘者头衔只在列表上判断。城市只分页，分页规则在 `classify_city`：不建区县表，也不因城市淘汰。标题 AI 三态；判成可点也不等于点开详情，其它城不点。每个搜词滚到底。同一轮共用一个时间戳，一搜词一份 jsonl，只追加。主键是 encryptId。详情里不再跑标题字面。HR 活跃见 ADR 0004，jsonl 见 ADR 0005。搜词和筛选条件改 `boss.yaml`。

**Code**: `src/boss_screen/rules.py`、`src/boss_screen/run.py`

**Considered Options**: 进详情后再用城市或标题字面淘汰；列表只滚前 50；在代码里写死详情次数。
