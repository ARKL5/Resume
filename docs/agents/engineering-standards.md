# Engineering standards

改代码或设计之前、以及审查时使用。和项目约束、自动化检查一起看。用词以 [`CONTEXT.md`](../../CONTEXT.md) 为准。

## Baseline

- **Follow the surroundings.** 跟仓库现有约定；必须偏离时写明原因。
- **Complete the task.** 交付被要求的行为，以及相关失败路径。
- **Delete with evidence.** 删除前核对调用方、校验、替代路径和兼容义务。
- **Test behaviour.** 断言来自需求、契约或缺陷。修 bug 时尽量先让回归在该缺陷上失败。测试按场景和期望结果命名。
- **Automate deterministic rules.** lint、类型、校验放进工具；入口写在 [`AGENTS.md`](../../AGENTS.md) 的 Verification。

## Project constraints

- **两份投递件。** 列看投递入口，不按 JD 另写一份。理由：[`docs/adr/0001-two-artifacts-by-entry.md`](../adr/0001-two-artifacts-by-entry.md)。
- **渠道事实一份。** 只写 [`docs/apply-research.md`](../apply-research.md)。理由：[`docs/adr/0002-research-in-docs.md`](../adr/0002-research-in-docs.md)。
- **Boss 在仓外。** 筛选、代聊只改 `D:\38993\Documents\get_jobs`。对照页 UI 在本仓 `screen/`。本仓仍是投递件，不是代聊后端。理由：[`docs/adr/0004-boss-get-jobs-outside-repo.md`](../adr/0004-boss-get-jobs-outside-repo.md)、[`docs/adr/0009-screen-own-page.md`](../adr/0009-screen-own-page.md)。
- **筛选与对照页。** 规则在列表，城市只分页，详情只 CPA；对照页按停驻展示，是工作台不是产品页。词用停驻 / 圈岗 / 城市分页。理由：ADR 0005、0006、0009。
- **证据。** 投递件经历与数字能在仓库或口述素材核对。开放题是投递件正文的真子集。
- **秘密与 git。** 秘密不进 git。只在本机 commit。
- **开聊。** 须本人明确说。对照页和 `SCREEN_ONLY` 都不开聊。
- **运行时。** 本仓 Python 用根目录 `.venv`。对照页 `screen/` 用 `npm run dev`（`:6867`）。get_jobs 用 Temurin 21。改对照页时读 frontend-design 与 vercel-react-best-practices。

## Smells

审查时对照 Fowler, *Refactoring*, ch. 3。发现要落到具体影响，再选相称的改法。

- **Mysterious Name:** 名字或它想表达的职责不清楚。
- **Duplicated Code:** 必须一起改的知识散在多处。
- **Feature Envy:** 行为更该靠近它所操作的数据。
- **Data Clumps:** 总是一起出现的值，应收成一个概念。
- **Primitive Obsession:** 该用领域类型表达含义或排除非法状态。
- **Repeated Switches:** 会一起变的分发逻辑应集中。
- **Shotgun Surgery:** 一条规则要改很多处。
- **Divergent Change:** 一个模块有互不相关的变化原因。
- **Speculative Generality:** 没有当前用途的抽象和钩子。
- **Message Chains:** 遍历把实现细节暴露出去。
- **Middle Man:** 委托既不加策略也不构成有用边界。
- **Refused Bequest:** 接口契约未兑现，或该改组合。

## Verification

按 [`AGENTS.md`](../../AGENTS.md) 的 Verification 跑适用检查，再对照本文件审 diff。报告结果和未解决问题。
