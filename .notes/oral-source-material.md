# 开放题源素材（草稿，待本人改口吻）

约束：只写两个仓库能撑住的句子。数字回指 artifact。不编经历。

核对底稿：

- `.notes/source-material-retail-bench.md`
- `.notes/source-material-rag-backend.md`

---

## 1. 项目口述

### 1.1 零售客服 Agent 评测仪器（retail-bench）

一句话：本地零售客服 Agent **评测仪器**，不是客服产品。每个 attempt 在私有可重置世界里跑 live Agent + live User Simulator，用冻结的 Expected Attempt Outcome 做确定性打分，并落盘证据。

可讲：

1. 写库不是聊天里说「好的」。路径是 preview 报价（不改世界）→ propose 绑定不可变提案 → Simulator 结构化授权 → commit 时才 deepcopy 工作副本提交。拒绝则世界不变，attempt 继续。
2. 公开目录正好 10 个工具。参数来自 Pydantic v2（`frozen=True, extra="forbid"`）。非法调用变成结构化错误观察回给 Agent，attempt 不因此终止。
3. Task Pass 必须三件事同时成立：受控完成、世界指纹一致、终局处置与 EAO 一致。金额用整数分。不是 LLM-as-a-judge。
4. 冻结配置（双槽 live `gemini-3-flash`，`max_inflight=8`）full-114：**92/114（80.7%）**。artifact：`20260811T165150Z-8d8046d5`。这是当时配置的一次 live，**不是 HEAD 的现行 KPI**，也不和外一份 ACI 的 97/114 连成一条涨分曲线。
5. 题目和 EAO 冻结后，只动 Agent 优化面（policy、工具描述、observation）。P0 对照 42 题 29/42（原失败 +9、随机 0 回归）。后面硬残差上再堆短 policy，hard 仍 1/12，战役停手。
6. 做过一次干净对照：只开 Agent 状态投影，22/32，不能归因成涨分；实现后来从产品树拿掉。

禁止：生产客服、上线 tau2、分别量化 System Prompt vs Tool Description、「预演在独立内存副本里写一遍」、把 80.7% 说成稳定通过率或 HEAD 成绩。

GitHub：https://github.com/ARKL5/retail-bench  
角色：独立个人项目。

### 1.2 所有者隔离的 RAG 知识库后端

一句话：可信本机、多用户**所有者隔离**的私人知识库 RAG 后端（作品集）。默认绑 `127.0.0.1`，不是公网 SaaS。

可讲：

1. 发布事务固定锁序：知识库 `FOR SHARE` → 文档 / 处理任务 / 索引构建 `FOR UPDATE`。同一事务写入切块并切换当前索引。热重建时**检索**仍扫旧指针；过期任务和旧 envelope 不能覆盖当前索引。
2. 活任务必须持执行令牌，终态清空。迟到结果靠 token fencing 挡住，不是教科书 OCC。
3. 检索用 `REPEATABLE READ` 固定当次当前索引。密集（pgvector）和稀疏（jieba + PG simple FTS）各进 Savepoint；一路失败降级，双路失败返回 `search_unavailable`，不是空成功。双路都有结果时 RRF（k=60）。
4. MinIO 只存原文：先 put，数据库失败后补偿 delete。解析进线程池。Markdown 用 markdown-it 标题 token 保留标题路径；PDF 按物理页切，不跨空页。
5. SSE 听到 `http.disconnect` 就取消生成、释放会话生成闸门。没有测到的 token 节省数字。
6. 引用必须落在本轮证据：越界编号不落库；提交时 `FOR SHARE` 复核证据文档还在。当前索引指针切换不推翻已冻结证据。

禁止：公网 SaaS、多租户/RBAC、熔断器、AST 引擎、自研 BM25、exactly-once、热重建期间「问答也可用」（只证明检索可用 + 本轮证据冻结）、用户量/QPS。

规模可讲：约 7.2k 源码、8.8k 测试、139 条测试、4 份 ADR。  
GitHub：https://github.com/ARKL5/rag-backend  
角色：独立个人项目。

---

## 2. 为什么投这类岗（Agent / LLM 应用，要写代码）

固定骨架，按 JD 只改第一句里的产品名：

我投的是能把模型接到真实工具和数据上的工程岗，不是纯调 prompt 的岗位。一边做 Agent：工具合同、授权、评测合同；一边做检索问答后端：索引发布、混合检索、引用必须能指回本轮证据。两个仓库都是我独立写完、有测试和可核对数字/行为的。希望在实习/校招里把这套接到你们的业务工具或知识库上，而不是从零再做一个聊天 demo。

按岗位类型可接的一句：

- Agent / 智能体：Exact-Write 和确定性评测。
- LLM / AI 应用：工具调用 + RAG 引用闸门。
- 不要用来投纯算法研究或纯产品岗。

---

## 3. 到岗与出勤（按清单列选用，不要混）

**实习列（实习 PDF、随时到岗）：**  
常驻杭州，每周 5 天，可随时到岗。远程仅当 JD 写明可远程。

**秋招列（校招 PDF、毕业入职）：**  
2027 届，浙江理工大学智能科学与技术，毕业时间 2027.06，到岗按校招批次（毕业入职）。秋招网申走主身份。

不要在秋招开放题里写「随时到岗、每周 5 天」；不要在实习开放题里写「明年 7 月才来」。

---

## 4. 简历里和仓库冲突、开放题不要沿用的两句

1. 「分别验证 System Prompt 与 Tool Description 的调优收益」——仓库没有分账对照。实际是 policy 与 description 一起改。
2. 「只读预演在独立内存副本中校验」——preview **不** deepcopy 世界；deepcopy 发生在 commit。

项目名「安全执行与评测系统」偏产品。口述用「评测仪器」。是否改简历 PDF，另定。
