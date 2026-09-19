# Boss 代聊只维护仓外 get_jobs

Boss 立即沟通只在本机 `D:\38993\Documents\get_jobs`（`loks666/get_jobs`）上改和跑：先筛选，再同一套开聊。源码不并进本仓——本仓仍是投递件，不是代聊后端。资源文档不再收录其它 Boss 代聊或招呼工具；缺口靠改这份 clone（Playwright 点网页，不是官方接口），不换工具。语义筛选由运行时调本机 CPA（`deepseek-v4.1-flash`），对话里不逐岗。提示词不追求一次写死：跑出关键词结果，本人在对照页看停驻、圈岗、再改偏好，多轮即可。Playwright 到此为止，不上远控 / 指纹浏览器 / 手机无障碍。对照页 UI 不在 get_jobs：本仓 `screen/` 独立圈阅页，只读 `:9527`。筛选引擎和代聊仍只改 get_jobs。见 ADR 0009。

**Code**: `docs/apply-research.md`

**Considered Options**: 源码 vendor / submodule 进本仓；文档里留 `geekgeekrun` / 扩展当备选或旁证。
