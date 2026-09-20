# Engineering standards

改代码或设计之前、以及审查时使用。

## Baseline

- **Follow the surroundings.** 跟仓库现有约定；必须偏离时写明原因。
- **Complete the task.** 交付被要求的行为，以及相关失败路径。
- **Delete with evidence.** 删除前核对调用方、校验、替代路径和兼容义务。
- **Test behaviour.** 断言来自需求、契约或缺陷。修 bug 时尽量先让回归在该缺陷上失败。测试按场景和期望结果命名。
- **Automate deterministic rules.** lint、类型、校验放进工具；入口写在 [`AGENTS.md`](../../AGENTS.md) 的 Verification。

## Project constraints

- **投递件。** 不按 JD 另写一份。岗位锁国内 Agent / LLM 应用（含要写代码的大模型应用）；城市杭州，JD 写明可远程才加。不改 PDF 项目 bullet。
- **边界。** 筛选与代聊只改 `boss/`，对照页只改 `screen/`。开聊须本人明确说。本仓维护投递件与投递进度，不是招聘平台、不是业务后端。
- **证据。** 经历与数字以 `resume/` JSON 为准。口述底稿仅当本人当轮指出才用。开放题只写投递件正文里已有的内容。

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
