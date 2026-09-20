# get_jobs 只留本机 Boss 筛选与代聊

本仓 `boss/`（由 `loks666/get_jobs` 裁成）只要 Boss 筛选和同一套代聊。原配置 UI（`front/`、`:6866`）删除，运行配置只在 `boss/boss.yaml`，对照页在 `screen/`。不连 sqlite。智联 / 51 / 猎聘接线拆除（Playwright 只开 Boss）。微信推送和投递分析不要。搜索附加条件、黑名单、已筛跳过、已开聊记录要能做。代聊先留接口：对当场点名的 encryptId 点立即沟通并发送招呼语（文案用 `boss.yaml` 的 `greeting`，可换）；图简历能力保留、默认不传。开聊须本人明确说；对照页和 `SCREEN_ONLY` 都不开聊。不自动回复 HR。不把已开聊当成第五处停驻。不再跟踪上游 fork，也不再单独维护仓外 get_jobs。

**Code**: `boss/`（`Boss.java`、`PlaywrightManager`）、`screen/`

**Considered Options**: 留下瘦配置页；对照页兼启停与改搜索词；只摘其它渠道 UI、启动仍开四站；把当前筛选没用到的搜索筛选 / 黑名单 / 代聊路径一并删掉。

**Consequences**: 不再跟上游 `front/` 与多渠道 worker 对齐。当前 sqlite 已删，登录靠 `browser-data`。
