# Boss 筛选：列表上的规则、城市分页、标题/JD 分步 AI

搜索杭州和上海，每个词把列表滚到底。结构化规则只做列表前置；城市只分页（工作地文案含杭州或上海，无区县表）。主键和点卡用 encryptId。标题语义走标题 AI，JD 语义走 JD AI。进了详情不再跑标题字面，例外见 ADR 0008。其它城市不点详情，卡片变成杭州/上海再补点。已终局再跑跳过；仅 HR 不活跃的规则淘汰在近 3 天时重开。词间和城间冷却 5 分钟；wait_time 下限 18 秒。列表 URL 上的人机验证也要停。字面与 jsonl 见 ADR 0010。

**Code**: `D:\38993\Documents\get_jobs\src\main\java\com\getjobs\worker\boss\Boss.java`、本仓 `screen/`

**Considered Options**: 详情后再做 HR/城市规则；每词 25/50 次详情上限；列表只滚前 50。
