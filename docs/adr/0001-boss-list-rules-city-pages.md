# Boss 筛选：列表上的规则、城市分页、标题/JD 分步 AI

搜索杭州和上海，每个词把列表滚到底。搜索条件含公司行业（互联网、人工智能、电子商务；yaml `codes.industry`）。结构化规则只做列表前置；城市只分页（工作地文案含杭州或上海，无区县表）。列表标签给标题 AI，岗位标题仍是主证据。招聘者头衔含猎头/招聘顾问/驻场或招聘者黑名单 → 规则淘汰（列表有头衔则点详情前，详情再跑一遍）。主键和点卡用 encryptId。标题 AI 三态：实现实习可点、产品经理/不确定待读、其余淘汰。过标题不等于点 JD；点详情次数由 `boss.yaml` 的 `detailLimit` 限制（试跑默认 0）。筛选结果在 `screenResultsDir`，一搜词一份 jsonl，文件名 `{同一次筛选的时间}_实习_搜词.jsonl`（一次筛选多个搜词前缀相同）；杭州/上海同一词续写，不覆盖历史。对照页只读切换。运行项（搜词、代码表、字面规则、提示词、AI 地址）都在 `boss/boss.yaml`。进了详情不再跑标题字面，例外见 ADR 0004。其它城市不点详情。词间和城间冷却见 yaml `keywordGapSeconds`；wait_time 下限 18 秒。列表 URL 上的人机验证也要停。停驻与 jsonl 字段见 ADR 0005。

**Code**: `boss/src/main/java/com/getjobs/worker/boss/Boss.java`、`screen/`

**Considered Options**: 详情后再做 HR/城市规则；每词 25/50 次详情上限；列表只滚前 50。
