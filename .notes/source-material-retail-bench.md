# 口述素材源：retail_bench（只读核对）

- 调研日期：2026-09-18
- 源仓库：`/home/ark/CODE/tau-retail-agent-eval-api`（Git remote `https://github.com/ARKL5/retail-bench.git`）
- 用途：本科生王中宇开放题 / 面试口述。硬约束：**简历和口述不能写仓库里没有的经历**。
- 方法：对照 `README.md`、`CONTEXT.md`、`docs/portfolio/*`、`src/retail_bench/`、`tests/`、`artifacts/`、git 作者与战役 commit。portfolio 草稿与代码/artifacts 冲突时，**以代码与 artifacts 为准**。
- 未改源仓库代码。不写可运行攻击/绕过。

权威优先级：

1. 现行行为：代码、类型、测试、CLI、`data/retail/` schema
2. 冻结分数：`artifacts/<run-id>/attempt-*/attempt.json`（评分权威）；同目录 `run.json` 可作计数，本调研已与 114 份 `attempt.json` 逐字段对齐
3. 口述草稿：`docs/portfolio/`（非产品权威；数字必须回指 artifact）

---

## 1. 一句话：这个项目实际是什么

**本地零售客服 Agent 评测仪器**，用来练评测驱动的 Agent 开发：每个 Evaluation Attempt 在**私有可重置零售世界**里跑 **live Agent + live User Simulator**，用冻结的 Expected Attempt Outcome（EAO）做确定性评分，并落盘可检查证据。

证据：`/home/ark/CODE/tau-retail-agent-eval-api/README.md` 第 1–3、39–40 行；`AGENTS.md` 第 3 行。

**不是：** 生产客服、SaaS、tau2 播放器、优化产品、排行榜、真人替代。产品 CLI 只有 `retail-bench run`，只走本机 CLIProxyAPI（`http://127.0.0.1:8317`），不提供 fake / 任意 endpoint / 多 provider 产品面。

---

## 2. 可公开讲的问题与机制

讲机制，不讲「上线了客服」。下面每条都能指到代码或测试。

### 2.1 先预演，再授权，再提交（Exact-Write）

问题：模型说「已退款 / 已改地址」，世界没变；或聊天里一句「好的」就被当成写成功。

机制（现行代码）：

1. **Preview** `preview_order_action`：与 propose **同构参数**，返回 `price_difference_cents`、`payment_validation`、`prospective_status`、`legal_actions`、`variant_plan`；**不 commit、不授权**。glossary 写明「不 deepcopy 世界」。测试：`tests/test_catalog.py` → `test_preview_order_action_does_not_mutate_and_quotes`。
2. **Propose** `propose_order_action` / `propose_customer_action`：只提交公开业务 action；Retail World 是唯一写构造器，产出 frozen `ExactWriteProposal`（`write_kind` + `target_refs` + `mutation_payload`）。
3. **Structured Authorization**：Tool Turn 把绑定提案交给 User Simulator 的 `authorize`（approve/deny），**不是** Agent 工具，也**不是**聊天里的「可以」。deny → `authorization_denied` 工具错误，世界不变，Attempt 继续。
4. **Atomic Commit**：approve 后 `RetailWorld.commit` 先 `deepcopy` 工作副本，校验再 apply，成功才写回；失败则工作副本丢弃。

路径：

- `src/retail_bench/domain/catalog.py`：`preview_order_action`（约 700–736 行）、`propose_order_action`（738–746）、`commit`（868–899）
- `src/retail_bench/runtime/tool_turn.py`：`_run_structured_authorization`（101–181 行）
- `src/retail_bench/domain/contracts.py`：`ExactWriteProposal`、`SimulatorAuthorization`
- 测试：`tests/test_authorization.py`
  - `test_exact_approval_commits_once_and_can_produce_task_pass`
  - `test_deny_is_a_normal_tool_result_and_leaves_world_unchanged`
  - `test_customer_end_while_awaiting_authorization_implicitly_denies_and_closes`
  - `test_simulator_cannot_mutate_bound_proposal_before_commit`（Sim 改 payload 不影响已绑定提案）
- 一轮至多一个 propose；preview+propose 同轮合法：`tests/test_tool_turn.py` → `test_tool_turn_preview_plus_one_propose_is_legal`；双 propose 整轮 `protocol_violation` 且无副作用：`tests/test_terminations.py` → `test_multiple_writes_reject_the_entire_turn_as_protocol_violation_without_side_effects`

**口述纠偏：** 不要说「预演在独立内存副本里跑一遍写」。`CONTEXT.md` 的 Order Action Preview 明确「不 deepcopy 世界、不 commit、不授权」。deepcopy 工作副本是 **commit** 路径。preview 只构造提案并投影报价。

### 2.2 Pydantic 工具 schema

公开目录恰好 **10** 个 Catalog Operation（不是「约 10」，HEAD `_OPERATIONS` 长度为 10）：

| 名 | category |
|---|---|
| `locate_customer` | locate |
| `list_orders` | list |
| `list_product_types` | list |
| `inspect_order` | inspect |
| `inspect_customer` | inspect |
| `inspect_product` | inspect |
| `preview_order_action` | preview |
| `propose_order_action` | propose |
| `propose_customer_action` | propose |
| `transfer_to_human` | transfer |

路径：`src/retail_bench/domain/catalog.py` `_OPERATIONS` / `RETAIL_CATALOG`（902–1043 行）。

模型可见投影：`CatalogOperation.tool_schema()` → OpenAI function calling 形，`parameters` 来自 `arguments.model_json_schema()`。参数基类 `Arguments`：`frozen=True, extra="forbid"`。校验失败 → `CatalogToolError("schema_invalid", ...)`，写回 Agent，**Attempt 不终止**。业务前置失败同理（如 pending 单上 `return_items` → `action_not_legal`）：`tests/test_tool_turn.py` → `test_tool_turn_business_precondition_is_tool_error_not_stop`。

Agent 输入：system = `data/retail/agent_policy.md`，tools = 上述 10 份 schema。`src/retail_bench/cli.py` 87–110 行；`src/retail_bench/cliproxy.py` `CLIProxyAgent.respond`（394–396 行）。

### 2.3 确定性评测条件（不是 LLM-as-judge）

**Task Pass** 三合取（缺一不可）：受控完成 ∧ World Match ∧ Terminal Disposition 与 EAO 一致。

代码：`src/retail_bench/domain/evaluator.py` `evaluate()`：

- `ProtocolViolation` / `RuntimeFailure` → `task_pass=False`，且 world/disposition 记 false
- `ControlledCompletion` → `world_match = world_matches(world, expected)`，`disposition_match = termination.disposition == expected.expected_terminal_disposition`，`task_pass = world_match and disposition_match`

World Match 权威只是 SHA-256 指纹：`src/retail_bench/domain/eao_authority.py` `world_fingerprint` / `world_matches`。金额走 Integer Cents（`money_to_cents`），`return_items` 当无序 id 袋排序后再哈希。

EAO 类型只有三字段：`task_id`、`expected_final_world_fingerprint`、`expected_terminal_disposition`。`data/retail/expected_attempt_outcomes.json` `schema_version` = `3.2.0`，`entries` 114 条。参与者可见 Task 只有 `id` + `user_scenario`（`tasks.json` 无 `evaluation_criteria`）。

测试：

- 客户结束 ≠ 自动通过：`tests/test_attempt_runtime.py` → `test_customer_end_produces_evidence_and_is_not_automatically_a_pass`
- 题与 EAO 一一对齐：`tests/test_load.py` → `test_thin_tasks_and_eao_are_fully_aligned`
- 改 observation 不能改世界、不能骗过指纹：`tests/test_isolation.py` → `test_tool_observation_mutations_do_not_rewrite_world_or_earn_task_pass`
- 并发 32 题、世界与 evidence 隔离：`tests/test_run_scheduler.py` → `test_high_inflight_is_real_and_attempt_worlds_and_evidence_are_isolated`
- `model_calls` 不进评分：`tests/test_model_calls.py` → `test_evaluate_result_is_independent_of_model_calls`

**评分隔离：** Agent 只看到 `agent_language_history()`（对话 + 工具观察）；Sim 只看到 `user_scenario` + Simulator History。EAO 挂在 `PreparedAttempt.expected` 上，仅 `evaluate()` 使用。未见把 EAO 注入 system prompt 的代码。`CONTEXT.md` Score Isolation。

CLI exit 0 只表示管道完成，不表示全过：`README.md` 第 25 行。离线 pytest 用进程内 double，**不证明** live 114 通过率。

---

## 3. 已核对数字

题量：**114**。`data/retail/tasks.json` 长度 114，id `"0"`…`"113"` 唯一；EAO `entries` 114；`load_tasks()` 与 `load_expected_outcomes()` 键集合被测试断言相等。

### 3.1 简历声称的 `20260811T165150Z-8d8046d5` —— **对得上**

路径：`/home/ark/CODE/tau-retail-agent-eval-api/artifacts/20260811T165150Z-8d8046d5/`

算法：读 `run.json` 的 `attempts[]`，数 `task_pass is true`；并与 114 份 `attempt.json` 的 `result.task_pass` 逐题比对，**mismatch = 0**。

| 项 | 值 | 来源 |
|---|---|---|
| 题量 | 114 | `run.json` attempts 长度；114 个 `attempt-*` 目录 |
| Task Pass | **92** | `sum(task_pass)` |
| 失败 | 22 | 同上 |
| 通过率 | **80.7018%**，口述可说 **80.7%**（92/114） | 92÷114 |
| Agent / Sim | 均为 live `gemini-3-flash` | `run.json` `metadata` |
| 并发 | `max_inflight=8`，`actual_worker_capacity=8` | 同上 |
| 终止 | `controlled_completion` 113；`runtime_failure` 1（task `12`） | 同上 |
| world_match false | 21 | 失败里除 disposition 单独失败外 |
| disposition_match false | 4（task `12`,`37`,`62`,`66`） | 同上 |

失败 task id（22）：`12, 18, 33, 36, 37, 42, 52, 56, 59, 62, 64, 66, 74, 76, 79, 88, 91, 96, 104, 107, 108, 113`。

**这是 Retail ACI cutover 之后、P0 display 之前的 full-114 单次 live。** 不是 HEAD 的现行 KPI。HEAD 之后还有 policy/description 改动与 ASP 删除（见第 4 节）。

portfolio 写 92/114、约 80.7%、artifact id：`docs/portfolio/interview-brief.md` 118–119 行、`docs/portfolio/post-aci-opt.md` 29 行。**与 artifacts 一致。**

### 3.2 旧 ACI 战役（实现面已换，不可与 92/114 纵向比作连续涨分）

同模型 `gemini-3-flash` 双槽、`--max-inflight 12`、full-114。数字与 `docs/portfolio/agent-opt-campaign.md` 一致。

| 标签 | artifact | pass | 率 | 核对 |
|---|---|---:|---:|---|
| R0 | `artifacts/20260810T123824Z-5a9c0206` | 83/114 | 72.8% | 通过 |
| C1 | `artifacts/20260810T133852Z-8714f3dd` | 94/114 | 82.5% | 通过 |
| C2 | `artifacts/20260810T140503Z-039d8825` | 97/114 | 85.1% | 通过 |

C1 相对 R0：新过 18 题、回退 7 题（净 +11）。C2 相对 C1：新过 9、回退 6（净 +3，含 live 浮动）。与已删除的 `.scratch/agent-opt-campaign/HISTORICAL-SUMMARY.md`（git `133f38b` 仍能 `git show`）一致。

C2 `run.json` 的 `bucket`：`None` 97 条（即 pass）、`A` 16、`B` 1、无 `C`。战役文「pass 97 · A 16 · B 1 · C 0」**对得上**。HEAD 已丢掉 bucket 产品语义（`d3b0515`），不要把 A/B/C 说成现行字段。

R0→C1→C2 的 `agent_prompt_digest` **和** `catalog_digest` **每次都变**。不是「只改 system prompt」的干净对照。

### 3.3 Post-ACI 对照子集（不是 full-114 外推）

| 阶段 | artifact | n | pass | 元数据要点 | 与草稿 |
|---|---|---:|---:|---|---|
| P0 display | `20260811T173219Z-bc78da47` | 42 | **29** | 相对 ACI 基线：prompt 与 catalog digest **都变** | 29/42 **对** |
| ASP on | `20260811T184333Z-3cbe44e0` | 32 | **22** | 与 P0 **同一** prompt/catalog digest；`agent_status_projection=True` | 22/32 **对** |
| P1 policy | `20260811T201732Z-77b929ea` | 32 | **21** | prompt **与** catalog digest 相对 P0 都变；ASP=False | 21/32 **对** |
| gemini-3.6-flash Agent | `20260811T174407Z-a44b99d1` | 29 | **15** | Agent `gemini-3.6-flash`，Sim 仍 `gemini-3-flash` | 15/29 **对** |
| gpt-5.6-sol | `20260811T175335Z-4d812136` | 12 | **0** | 12/12 `runtime_failure`，diagnostic 全文 `CLIProxyAPI tool_calls must be a list` | 0/12 **对** |
| deepseek 串行 | `20260811T205631Z-746d7f49` | 32 | **20** | 双槽 `deepseek-v4-flash`，`max_inflight=1` | 20/32 **对** |

P0 42 题构成（由 task 集合对 ACI 基线失败集求交，不是口述）：

- 原失败 22 题 = 基线 22 个 fail **全部**纳入
- 随机 20 题 = 基线已通过的 20 题
- 原失败现通过 **9**：`12,33,36,37,62,66,96,108,113`
- 随机回归 **0**
- 草稿「+9、随机 0 回归 → 29/42」**对得上**

P1 / ASP / deepseek 共用同一 32 题序：hard 12 = `18,42,52,56,59,64,74,79,88,91,104,107`，其后 sample 20。

- P1：hard **1/12**（仅 `79` 过），sample **20/20** → 21/32。草稿「hard 1/12=79」意为 **题号 79**，不是 79%。
- ASP：hard **2/12**（`52`,`79`），sample 20/20 → 22/32。战役文写这两次救回**不可归因**为机制（单次方差）。
- deepseek 串行：hard 2/12，sample 18/20（`67`,`92` 回归）→ 20/32。

**deepseek 并发全灭不要说成模型地板：**

- `20260811T205254Z-234e91ae`：32/32 `runtime_failure`，429 Too Many Requests，`max_inflight=8`
- `20260811T205341Z-c4a8ebff`：同上，`max_inflight=2`

sol 全灭对应代码：`src/retail_bench/cliproxy.py` 398–401 行，`tool_calls` 非 list 就 `RuntimeError("CLIProxyAPI tool_calls must be a list")`。这是 **wire/interop**，不是业务 Task Pass 地板。

### 3.4 草稿里有、仓库对不上或不该当数字用的

| 草稿说法 | 核对 |
|---|---|
| 公开目录「约 10 个工具」 | HEAD 恰好 10。说「约」过于含糊，可改「10」。 |
| Context 组成「静态 policy+tools ~20k 字；conv p50~14k / max~32k；tool 消息占 conv ~68%」 | 仅出现在已删 `.scratch/post-aci-opt-experiment/CLOSING.md`，**未单独立 artifact**。口述不要报这些字数。 |
| 「夹心分析 L0–L4」 | 工作树战役文已削薄；细节只在 git 历史 `HISTORICAL-SUMMARY.md`。可说「当时用分层失败归因」，不要把 L0–L4 说成现行方法或有独立脚本仍在 HEAD。 |
| 92/114 是 HEAD 成绩 | **不是**。那是 2026-08-11 该 artifact 的冻结配置。 |

复算命令（源仓库根）：

```bash
python3 -c "
import json
from pathlib import Path
p=Path('artifacts/20260811T165150Z-8d8046d5/run.json')
a=json.loads(p.read_text())['attempts']
print(sum(x['task_pass'] for x in a), '/', len(a))
"
```

---

## 4. 控制实验结论（只写有证据的）

### 4.1 「System Prompt vs Tool Description」分账 —— **未在仓库找到**

简历 `resume/resume-data-campus.json` 第 4 条：

> 在题目与目标订单数据冻结的前提下做控制变量实验，**分别验证 System Prompt 与 Tool Description** 的调优收益……

`source_note` 指向 `eval-driven-dev.md`。该文件只说「一次一个杠杆」「只改 Agent 优化面：policy、catalog 投影、observation 形状」，**没有** prompt-only vs description-only 的对照表或 artifact。

仓库内实际看到的是 **共真、一起改**：

- ACI 票 `04-policy-and-description-cotruth`（git `0a2e0fc:.scratch/retail-aci-impl/issues/04-policy-and-description-cotruth.md`，工作树已删）：policy 短文 + 每个 tool description 必须含「何时用 / 不做 / 一例」；二者不抢 schema/observation 权威。
- P0 commit `ee33a00`：同时改 `data/retail/agent_policy.md` 与 `src/retail_bench/domain/catalog.py`（description / `variant_plan`）。
- P1 commit `8046f6a`：同样同时改 policy 与 catalog 描述；随后 `e8ccf75`、`b713d06` 只动 policy（无单独 live full 对照把「只改 policy」从「同时改 description」里拆开）。
- 凡 full-114 或 P0/P1 提分 run，`run.json` 里 `agent_prompt_digest` 与 `catalog_digest` **同时变化**。

旧战役历史摘要（已删文件，git 仍在）甚至写：**「禁止默认只改 system prompt」。**

因此：**不能**口述「我做了控制变量，分别量化了 System Prompt 和 Tool Description 的收益」。能说的是：优化面允许改这两处（外加 observation 形状），实际战役把它们当共真一起收紧；**没有**留下只动其中一个的对照分数。

「长 Prompt 边际递减、停手」有证据，但是 **战役停手判决**，不是 prompt vs description 的分账结果。证据：`docs/portfolio/post-aci-opt.md` 停手段；P1 对照 32 题 hard 仍 1/12。

### 4.2 真正干净的对照：ASP（状态投影）on/off

唯一「同 policy digest、同 catalog digest、只改一项」的 live 对照：

- 关：P0 配置（digest `fde845c8…` / `e73a4dbc…`），42 题里的困难残差随后收成 32 题集
- 开：`artifacts/20260811T184333Z-3cbe44e0`，`agent_status_projection=True`，**22/32**（hard 2/12）

战役结论：hard +2 **不可归因**（方差 / retry）；多写场景投影可见但未遵循；**不要说「ASP 提升了通过率」**。HEAD 已删除实现（`3d7f82a feat: land eval-trust decisions and drop ASP`）；`src/retail_bench/runtime/` 无 `agent_status_projection.py`。面试若问，答「阴性消融，默认 off，后来从产品树拿掉」。

### 4.3 有证据、但是打包杠杆（不要说成单因子）

- **P0 display**（`ee33a00` + 42 题 artifact）：policy + tool description + preview `variant_plan`。困难 +9、随机 0 回归。可讲「短而具体的界面提示仍有局部价值」。
- **P1 短 policy**（`8046f6a`…`b713d06` + 32 题）：deny-retry / horizon / variant-match，同时改了 Field description。hard 未达「≥3/12」门槛 → **停止 AOS 提分战役**。
- **换模型抽检**：3.6 未打开困难地板；sol 是 wire 全灭；deepseek 串行与 flash 同集 20/32 vs 21/32，差距在单次噪声量级——且 deepseek 并发被 429 打成 0/32，不能拿 0 当能力。

Agent Optimization Surface 门禁（可讲）：允许 policy / 工具描述 / observation 形状；**禁止为刷分改 EAO/tasks**。`docs/portfolio/eval-driven-dev.md`；`CONTEXT.md` Score Isolation。

---

## 5. 技术栈与个人角色

| 项 | 仓库事实 |
|---|---|
| 包名 / 版本 | `retail-bench` 0.1.0，`pyproject.toml` |
| 语言 | Python `>=3.12,<3.14`，`uv` |
| 运行时依赖 | `pydantic>=2.10,<3`，`typer`，`httpx[socks]` |
| 开发门禁 | `pytest`，`ruff`，`pyright` strict |
| Live 调用 | 本机 CLIProxyAPI Chat Completions；环境变量 `RETAIL_BENCH_API_KEY` / `RETAIL_BENCH_AGENT_MODEL` / `RETAIL_BENCH_SIM_MODEL`。`docs/model-configuration.md` |
| 数据 | `data/retail/{tasks.json,expected_attempt_outcomes.json,db.json,agent_policy.md,simulator_prompt.md}` |
| 谱系 | 改编自 `sierra-research/tau2-bench` retail 子集；**本地分叉**。`THIRD_PARTY_NOTICES.md`（MIT, Copyright 2025 Sierra Research） |
| 本仓许可 | MIT，`LICENSE` Copyright (c) 2026 **ARKL5** |
| 作者 | `git log` 唯一作者 `ARKL5 <389932458@qq.com>`（HEAD 667 commit）。无 `CONTRIBUTING.md`、无 `pyproject` authors 字段、无合作者提交 |
| 角色结论 | **独立个人项目**（以 git 作者为准）。未在仓库找到第二作者或组织署名 |
| Git 时间 | 首 commit `ee947c9` 2026-04-30「initialize tau retail eval baseline」；AOS 战役停于 2026-08-11 的 artifacts / 2026-08-12 的 commits；HEAD 仍有 2026-09-16 的测试清理。简历写「2026.06–2026.08」**不是** git 全生命周期 |

早期历史有 `feat: add tau2 runner core`（2026-05-01）。现行 README 明确 **不是 tau2 播放器**。口述用现行身份，不要把早期 runner 说成「我上线了 tau2」。

---

## 6. 面试官可能追问：仓库能答 / 答不了

### 能答（指到文件）

- Task Pass 为什么不是看聊天？`evaluator.py` + `test_customer_end_produces_evidence_and_is_not_automatically_a_pass`
- 为什么聊天「可以」不能写库？`tool_turn.py` 授权协议；`test_deny_is_a_normal_tool_result_and_leaves_world_unchanged`
- 预演会不会改世界？`test_preview_order_action_does_not_mutate_and_quotes`
- 如何防止 Sim 改绑提案？`test_simulator_cannot_mutate_bound_proposal_before_commit`
- 如何防止 Agent 改 tool observation 骗分？`test_isolation.py`
- 并发会不会串世界？`test_high_inflight_is_real_and_attempt_worlds_and_evidence_are_isolated`（32 题、max_inflight 16；**不**证明 live 114 质量）
- 92/114 怎么来的？第 3.1 节算法 + artifact 路径；模型 id 与并发写在 `run.json` metadata
- 为什么不改 EAO 刷分？会换合同、毁掉版本可比性。ACI cutover 时 EAO 曾一次性迁到 action-aligned（commit `0a2e0fc` 改了 `expected_attempt_outcomes.json`）——那是 **换工具合同**，不是同合同刷分
- 和 τ-bench / tau2 关系？灵感与 retail 数据谱系，见 `THIRD_PARTY_NOTICES.md`；本地删了 `evaluation_criteria`，EAO 是本地权威
- ASP 为什么做了又删？阴性对照 + HEAD `3d7f82a`
- sol 0/12？`cliproxy.py` 对非 list `tool_calls` 抛错，artifact diagnostic 原文一致

### 仓库答不了（缺口，不要编）

- 统计显著性、Pass@k、多次复测方差（除战役文对 C1→C2 新过/回退的粗算）
- System Prompt **单独** vs Tool Description **单独** 的效应量
- 生产流量、延迟 SLO、真实客户授权/合规
- 与官方 tau2 排行榜数字对比、drop-in 兼容
- 114 是否「评测可信的条件」（README 明确：114 是冷冻测量仪题量，不是可信条件）
- HEAD 现行 full-114 live 分数（战役后代码又改了，未见新的 full-114 artifact）
- 上下文 token 精确分布（CLOSING 里的 20k/14k/68% **未落盘**）
- 合作者、实习雇主、上线业务
- CLIProxyAPI 本身的实现与 SLA（本仓只当本机 seam）

---

## 7. 建议写进口述的 4–6 条 bullet

每条 ≤80 字，附证据路径（相对源仓库根）。

1. 本地零售客服 Agent 评测仪器：私有世界里跑 live Agent + Sim，用冻结 EAO 打分并落盘证据，不是客服产品。（`README.md`）
2. 写路径是 preview 报价（不改世界）→ propose 绑定提案 → Sim 结构化授权 → commit；口头「好的」不能写库。（`catalog.py`、`tool_turn.py`、`tests/test_authorization.py`）
3. 10 个工具参数来自 Pydantic frozen schema；非法调用变结构化错误观察，Attempt 继续。（`catalog.py` `tool_schema`、`tests/test_tool_turn.py`）
4. 通过须受控完成、世界指纹与终局处置一致。冻结双槽 flash full-114 为 92/114（80.7%），非 HEAD KPI。（`evaluator.py`、`artifacts/20260811T165150Z-8d8046d5`）
5. 冻结 EAO 后只动优化面。P0 对照 42 题 29/42（原失败 +9、随机 0 回归）；ASP 阴性且 HEAD 已删。（`ee33a00`、`artifacts/20260811T173219Z-bc78da47`）
6. 残差拆成 Agent 选错 / Sim 改口 / EAO 合同张力，而不是再堆长 policy。P1 的 hard 仍 1/12，战役停手。（`docs/portfolio/post-aci-opt.md`、`artifacts/20260811T201732Z-77b929ea`）

---

## 8. 明确禁止写进素材的夸大

| 禁止说法 | 原因 |
|---|---|
| 生产客服 / 上线客服 / 安全执行系统 / 越权防护产品 | README：学习/实验/作品集尺度的**本地仪器**。单客户锁与授权是评测协议，不是生产 IAM |
| 「上线 tau2」/ tau2 播放器 / 官方 bench 兼容 | `README.md` 声称边界；`THIRD_PARTY_NOTICES.md` 本地分叉 |
| 「我把模型优化到 95%+」或把旧 ACI **97** 与新 ACI **92** 连成一条涨分曲线 | 工具面与 EAO 表达已换；portfolio 自己也禁止这样讲 |
| 「分别验证 System Prompt 与 Tool Description 的调优收益」 | **未在仓库找到**独立对照。简历第 4 条应删或改成「policy 与 tool description 共真一起收紧」 |
| 「ASP 提升了通过率」 | 22/32 且战役判定不可归因；HEAD 已删 |
| 子集 29/42、21/32 外推成 full-114 | 禁止 |
| 把 80.7% 说成 HEAD、稳定通过率、跨模型普遍质量、统计显著 | 单次/少数次本地 live；配置写在该 artifact metadata |
| 「预演在独立内存副本校验」当作 preview 的语义 | preview 不 deepcopy 世界；deepcopy 在 commit |
| 「自纠错闭环」若暗示模型学会了 EAO | 只是 schema/业务错误观察回传，Attempt 继续 |
| 「规避 LLM-as-judge」若暗示自己发明了 tau2 | 本地指纹匹配；谱系要致谢上游 |
| 把 pytest 高并发隔离说成 live 114 质量证明 | README 写明不证明 |
| 把 deepseek 并发 0/32 说成模型不行 | 全是 429 |
| 把 sol 0/12 说成业务地板 | diagnostic 是 `tool_calls must be a list` |
| 合作项目、团队、实习业务成果 | git 唯一作者 ARKL5 |
| 上下文 20k/68% 等未落盘字数 | 仅删掉的 scratch，禁止 |
| 「114 证明评测可信」 | README：114 是冷冻题量，不是可信条件 |

### 与现行简历条目的冲突（供改简历，本文件不改简历）

`RAG-BACKEN/resume/resume-data-campus.json` 项目名「零售客服 Agent **安全执行**与评测系统」偏产品化，建议改回「评测仪器」。第 1 条 preview「独立内存副本」与 `CONTEXT.md` 冲突。第 3 条 92/114 数字**核对通过**，但须加冻结配置 / artifact id / 非 HEAD。第 4 条「分别验证 System Prompt 与 Tool Description」**应视为无证据，不能用**。

---

## 附：关键路径速查

| 用途 | 路径 |
|---|---|
| 身份与声称边界 | `README.md` |
| 术语 | `CONTEXT.md` |
| 口述草稿（非权威） | `docs/portfolio/interview-brief.md` |
| 怎么用评测 | `docs/portfolio/eval-driven-dev.md` |
| 旧 ACI 分数带 | `docs/portfolio/agent-opt-campaign.md` + `artifacts/20260810T12*` / `13*` / `14*` |
| 新 ACI 战役 | `docs/portfolio/post-aci-opt.md` |
| 工具 / 写路径 | `src/retail_bench/domain/catalog.py` |
| 授权编排 | `src/retail_bench/runtime/tool_turn.py` |
| 评分 | `src/retail_bench/domain/evaluator.py` |
| 指纹 | `src/retail_bench/domain/eao_authority.py` |
| 隔离执行 | `src/retail_bench/runtime/attempt_runtime.py` |
| 授权测试 | `tests/test_authorization.py` |
| Full-114 冻结点 | `artifacts/20260811T165150Z-8d8046d5` |
