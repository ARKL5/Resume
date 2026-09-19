# 投递资源

再核：2026-09-19。工具 / 渠道事实只写这一份。

渠道只有两类：企业 / ATS **专属网申**，Boss **立即沟通**。Boss「网申·直投」跳过。实习僧、智联、51、猎聘、拉勾、应届生、高校 24365 不投。

可信：源能打开、2026 仍更新或商店在架、能说清权限和动作。远控 IP、停更约一年、评价普遍不能用的不进用法。

本机可跑代聊 / 代提交。登录态接法不限，以能跑通为准。秘密不提交进 git。要对证时打开来源 URL。

## 先用这些

| 目的 | 用 |
|---|---|
| 网申只填 | Edge **牛客网申助手** |
| 北森 / Moka 填不动 | **塔塔网申**；再不行求职喵或 OfferLink |
| 网申真提交 | `HA7CH/job-pro` |
| Boss 代聊 | `loks666/get_jobs` |
| Boss 要桌面 UI | `geekgeekrun/geekgeekrun` |
| Boss 要浏览器扩展 | Ocyss `boss-helper` GitHub 侧载 |

## 专属网申

公开没有维护中的阿里 / 字节 / 网易公司专用填表油猴。能用的是泛填扩展，或 `job-pro` 对接自研站 / 北森 / Moka / 飞书。滴滴校园入口跳 **Moka**。

校园站次数（填表前看官网 FAQ）：字节校招全年 4 次、同时最多 2 岗；阿里每 BG 最多 2 意向、投后不可改；百度同项目一次 1 岗。

开放题只写 [口述素材](../.notes/oral-source-material.md) 能撑住的句子。

### 只填表

| 工具 | 源 | 点名 | 说明 |
|---|---|---|---|
| 牛客网申助手 | Edge `macoagnpgdmmcpnkpmiplpfompjkfdbe`。Chrome 商店无同名。介绍页 https://www.nowcoder.com/my/resume-plugin-intro 会渲染成 **NowClaw** 桌面端，不要从该页下安装包 | 字节、腾讯、阿里、美团、百度、京东、快手、网易、滴滴、小红书等 | 官方帖：只填有标准答案的字段。Edge v1.0.8（2026-08-12），约 3.3 万 |
| 塔塔网申 | https://www.tatawangshen.com/ ；Chrome 商店 | 评价常点北森 / Moka | v0.8.3（2026-09-17）。评价：只能填、开放题会乱编。不买人工代投 |
| OfferLink | Edge `ciahffmjmolgknpmafahjanlfoblbofk` | 腾讯 / 阿里 / 字节 + Moka / 飞书 / 北森 / 用友大易 | 约 1.3 万。按钮「自动填充此页面」 |
| 求职喵 / 填填鸭 | 同一 Edge id `pmnkgkbolhdhgacoilieacaefhbpabcp` | **北森 / Moka / 大易** | v1.2.5（2026-09-06），约 784。要登录 + 云端。商店还写 51Job，那页不用于本仓渠道 |
| Resume Pro | https://github.com/TshyGO/resume-form-assistant-plugin | 泛企业网申 | ~95 star；Release 2026-09-05。Excel 模板 + 页内注入 |
| 职聘通 zip | https://ououguai-cloud.github.io/job-hunter/extension.html | 任意企业官网 | 低权限只填。同站「一键投递引擎」是另一套 |
| TalenCat | Chrome `hecdlpbbjhibhneefbdbcgbjclomoaif` | 泛 ATS | 明文不代提交；开放题要人改 |

### 真提交

| 工具 | 源 | 打哪 | 说明 |
|---|---|---|---|
| `HA7CH/job-pro` | https://github.com/HA7CH/job-pro ；https://job.ha7ch.com/ | 文档约 50 适配器。自研：腾讯、字节、阿里、美团、小红书、京东、快手、百度、网易、滴滴、拼多多等。Moka / 北森 / 飞书 ATSX 见仓库 docs | MV3 导出登录态 + CLI。公开几乎唯一的校园 / ATS 真 POST。文档把滴滴写成自研；入口实际跳 Moka，以登录后页为准 |
| 职聘通「一键投递引擎」 | 同职聘通站点 | 企业官网 | 本机 Node 开浏览器，提交前截图确认。不要和 zip 只填扩展当成一套 |
| 牛客「一键投递全网职位」 | https://www.nowcoder.com/jobs/deliver-more-job | 绑定企业官网账号后批量 | 要官网账号 |

人工代投（塔塔、求职方舟 100 家 ¥1500）不是脚本，不收录为用法。

## Boss

默认按钮「立即沟通」= **开聊**，不是申请。附件简历须双方同意。无官方打招呼插件。用户协议禁未经许可第三方插件 / 外挂；本轮仍收录并跑代聊，以开上聊为准。

HR 丢来官网 / Moka / 北森链接 → 改走专属网申，不是 Boss 直投。

招呼语若脚本要默认文案，用：

> 您好，浙江理工大学，常驻杭州，每周 5 天，随时到岗。独立做过零售客服 Agent：在 tau2-bench 上做确定性评测和优化，任务通过率80.7%（92/114），另有用户隔离的可靠 RAG 后端。期待沟通。

数字只描述该 artifact，不是 HEAD KPI。

### 代聊

优先源码仍更新的；商店扩展次之。仓内若还带智联 / 51 / 猎聘，那些渠道不用。

| 工具 | 源 | 动作 | 为何进正文 |
|---|---|---|---|
| `loks666/get_jobs` | https://github.com/loks666/get_jobs | Playwright + Cookie。Boss 打招呼 + 图简历 | ~8.5k；2026-09-16 仍更。**优先这套** |
| `geekgeekrun/geekgeekrun` | https://github.com/geekgeekrun/geekgeekrun | Electron + Puppeteer。自动开聊、已读不回再聊 | ~2.4k。要桌面 UI 时用 |
| Ocyss/boss-helper | https://github.com/Ocyss/boss-helper ；Chrome `ogkmgjbagackkdlcibcailacnncgonbn` | 批量沟通 + GPT 打招呼；要 cookies | GitHub v0.5.2（2026-08）。商店页有 unavailable 旁证，优先 GitHub 侧载 |
| `yangfeng20/ai-job` | https://github.com/yangfeng20/ai-job ；GF `527733` | 批量沟通、发简历、换联系方式、AI 坐席 | GH ~677；GF ~1298；2026-05。旧作 Batch Push GF `468125` 已停适应当页 |
| BOSS海投助手 | Chrome `ngmdahaccemclbokmkhbdbklikbohepn` | 批量投递与自动沟通 | ~491；v1.3.3 / 2026-09 |
| 菜大师boss海投助手 | GF `581725` | 海投 | 188 装；2026-09-11 |
| 觅星小臣 BOSS海投助手 | 脚本猫 `5970` | 海投 | ~4k 装；约 3 个月前仍更 |
| BossHunter | https://github.com/shengjidaguai-china/BossHunter | CDP；确认后再发 | v2.4.0 / 2026-09 |
| 一键职达 | https://yjzd.work/ | Boss 自动投 + AI 打招呼 / 自动回复；指纹浏览器 | 桌面商业软件。13 平台里只用 Boss |
| 职投助手 ZhiTou | Chrome `nffekoimgbildcbhnhgnncdgbkoblidc` | 自动招呼；目前 Boss | ~141 |
| AI工作快搜 | Chrome `habgifainjngdknnhjhfigbdjkoealdi` | 自动投递 / 沟通 | ~202；cookies + webRequest |
| `OpenFuckJob/FuckJob` | https://github.com/OpenFuckJob/FuckJob | Tauri；扫码、批量沟通 | 74 star |
| 投投马 | Chrome `mbgdhklndilcojhbgaalelolcaiojleb` | 自动打招呼 | ~132；标 debugger |
| 鹿鹿 Lulu | https://github.com/fanyangcloud/LuluAgent | Android 无障碍代沟通 | Releases 2026-09-14。本机是 Windows，只在要跑手机端时用 |

### 只辅助、不代发

| 工具 | 源 | 做什么 |
|---|---|---|
| AI求职助理 | Chrome `bhoegllmjgnpgnkfephahbibajklkaag` | 生成招呼，明文不自动发送 |
| Job Hunter AI | Chrome `lljgdcaoaonebbcmdjglkkmejbjmkfbe` | 填进对话框，商店写不自动发送 |
| BOSS直聘-外包标注 | Greasy Fork，作者「一袋米」，2026-09 | 标外包 |
| JD/HR 提取 | GF `546240` | 提取信息 |
| 岗位发布时间 | GF `541585` | 显示时间 |

## 不进正文

| 类 | 例子 | 原因 |
|---|---|---|
| 远控 | GF `569496` / 脚本猫 `5604`（`@connect 119.45.5.172`） | 远程 IP |
| 停更 | GF `428962`（2021）、`464791`（2023）、忒星 `481022`（2024-07）、Ocyss 油猴档、实习僧网申助手（2025-10）、超级网申（2025-09） | 超过约一年或作者声明改扩展 |
| 评价不能用 | 鼠鼠求职 Chrome `nfecpnkjbaecdcljillneejebdhogbel` | 商店评价多写不能用 |
| 存活未钉死 | 脚本猫曾 `5839` Yangshengzhou | GF 已删；猫站时通时 404 |
| 无公开源码 | NowClaw | 牛客介绍页桌面端，不优先 |
| 自配映射、未钉 2026 维护 | jobfill、auto-ws、OpenJobAutofill、Job-Submit、1lck | 侧载只填，不是本轮优先 |
| 错渠道 | 51 / 智联 / 应届生 / 实习僧站内代投 | 本轮不投这些渠道 |
| HR 端 | Boss Plus、Boss Say Hi、GF `422508` | 反向，不是求职 |
| 1 commit / 开放题乱写 | CampusApply-Agent | 不可信 |

## 本机怎么用

1. **网申填表：** Edge 装牛客网申助手。北森 / Moka 再试塔塔或求职喵。
2. **网申真提交：** `job-pro`。登录态用它的 session 扩展、调试端口或本地导出，哪种能跑通用哪种。
3. **Boss 代聊：** 优先 `get_jobs`。要 UI 用 geekgeekrun。要扩展用 Ocyss 侧载。
4. 登录态接法不限。不要 `git add` cookie / 密码 / session 文件。

## 来源

协议：https://www.zhipin.com/web/common/protocol/protocol-2019-09-30.html

网申填表：https://microsoftedge.microsoft.com/addons/detail/牛客网申助手/macoagnpgdmmcpnkpmiplpfompjkfdbe ；https://www.tatawangshen.com/ ；https://microsoftedge.microsoft.com/addons/detail/offerlink-简历自动填写助手/ciahffmjmolgknpmafahjanlfoblbofk ；https://microsoftedge.microsoft.com/addons/detail/求职喵·网申自动填简历神器/pmnkgkbolhdhgacoilieacaefhbpabcp ；https://github.com/TshyGO/resume-form-assistant-plugin ；https://github.com/HA7CH/job-pro

Boss：https://github.com/loks666/get_jobs ；https://github.com/geekgeekrun/geekgeekrun ；https://github.com/Ocyss/boss-helper ；https://github.com/yangfeng20/ai-job ；https://github.com/shengjidaguai-china/BossHunter ；https://yjzd.work/ ；https://greasyfork.org/zh-CN/scripts/by-site/zhipin.com ；https://scriptcat.org/zh-CN/script-show-page/5970

校招入口（网申）：https://campus-talent.alibaba.com/ ；https://jobs.bytedance.com/campus/position ；https://campus.163.com/ ；https://join.qq.com/ ；http://campus.didiglobal.com
