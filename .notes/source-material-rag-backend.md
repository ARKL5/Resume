# 口述素材：私人知识库 RAG 后端

用途：本科生王中宇开放题 / 面试口述。只收录仓库可核对事实。未在仓库找到的经历不写。

仓库：`/home/ark/CODE/RAG-BACKEN`（GitHub: https://github.com/ARKL5/rag-backend）  
领域词权威：`CONTEXT.md`。工程边界：`README.md`、`docs/adr/`。

---

## 1. 一句话边界

可信本机、多用户所有者隔离的私人知识库 RAG 后端（本科实习 / 求职作品集）；默认只绑 `127.0.0.1`，不是公网 SaaS，也不是生产平台。

证据：`README.md` 第 1–21 行；`AGENTS.md` 第 3 行；`docker-compose.yml` 端口绑定 `127.0.0.1:8000/5432/9000`；`.env.example` `API_HOST=127.0.0.1`。

---

## 2. 可公开讲的机制

口述时用 `CONTEXT.md` 的词：知识库、处理任务、执行令牌、索引构建、当前索引、本轮证据、生成闸门、引用、迟到结果、所有者隔离。不要说租户 / 多租户 / RBAC / 候选索引 / 证据袋。

### 锁顺序与原子索引切换

发布事务固定锁序：知识库 `FOR SHARE` → 文档 `FOR UPDATE` → 处理任务 `FOR UPDATE` → 该文档全部索引构建 `FOR UPDATE`。同一事务插入新索引构建与切块（含 embedding、`search_vector`），按执行令牌把处理任务写成成功，再把 `documents.current_index_build_id` 切到新构建，并删除该文档其余构建。外部 I/O（MinIO 读原文、嵌入）在持锁事务之外。

证据：`src/rag_backend/index/indexing.py` `_publish`；`docs/adr/0001-postgresql-transaction-core-with-minio-originals.md`；`docs/adr/0003-parent-locks-serialize-child-changes-and-deletion.md`。

### 执行令牌 fencing（不要说成教科书 OCC）

活处理任务必须持有执行令牌，终态必须清空。领取、心跳续约、成功发布都是 `WHERE execution_token=:token` 条件写入。一文档最多一个 queued/running 任务（部分唯一索引）。过期租约恢复会轮换令牌；接管次数上限 2，超限写成失败终态 `execution_lost`（对外投影 `processing_failed`），当前索引不变。

证据：`src/rag_backend/processing/execution.py` `_claim` / `_complete_success` / `recover_expired`；`migrations/versions/0001_v1_baseline.py` `uq_processing_jobs_one_active`、`ck_processing_job_execution`；`docs/adr/0004-processing-job-execution-ownership.md`。

简历里的「乐观并发控制」在代码 / ADR 中没有这个名字。更贴仓库的说法是：持锁串行化发布 + 执行令牌 fencing 挡住迟到结果。

### Hybrid Search + RRF + Savepoint 降级

检索第二阶段用 `REPEATABLE READ` 快照解析「当前索引」集合。密集路：pgvector 余弦（`1 - (embedding <=> vector)`，阈值 0.35）。稀疏路：jieba 预分词后 `to_tsvector('simple')` / `plainto_tsquery`（不是自研 BM25）。两路各包 `connection.begin_nested()`（Savepoint）；一路 SQL/供应失败只回滚该 Savepoint，另一路继续。嵌入调用失败则跳过密集路。双路都失败 → `SearchUnavailableError`，不是空成功。双路都有结果时 `fuse_rrf(..., k=60)`。公开检索条目不带分数、不标哪一路。

证据：`src/rag_backend/search/retrieval.py` `PgRetrievalService.search`；`src/rag_backend/search/fusion.py` `RRF_K = 60`；`src/rag_backend/runtime/lexical.py`。

「熔断」未在仓库找到独立熔断器状态机；实现是单次请求的 try/except 降级。嵌入客户端 `httpx` 超时 30 秒，但检索层捕获的是任意 `Exception`，不是只处理超时。

### MinIO 补偿

MinIO 只存文档绑定的原始内容；对象 I/O 不占用 PostgreSQL 长事务。入库先 `put`，数据库插入失败（含知识库已删、digest 冲突、其它异常）后 `delete` 补偿。`delete` 吞掉异常，明确是 best-effort。原文「不可变」是应用约定（`content_digest` + `object_key`），MinIO 未开 Object Lock。

证据：`src/rag_backend/documents/documents.py` `accept`；`src/rag_backend/runtime/object_store.py`；`docs/adr/0001-postgresql-transaction-core-with-minio-originals.md`。

### 解析与事件循环

`derive_sources` 整段解析/切块 `asyncio.to_thread`。Markdown 用 `markdown-it-py` 的 heading token 建标题栈，保留 `title_path`。PDF 按物理页 `extract_text`，切块不跨页。超长块在段落/标点（含中文句号、逗号）上回退。切块 800 / overlap 120。

证据：`src/rag_backend/index/text_sources.py`。简历「AST 解析」偏满：仓库是 markdown-it token，不是树解析器 AST。

### SSE 断开取消

提问走 FastAPI SSE（`accepted` / `delta` / `completed` / `failed`）。`_DisconnectSupervisedStreamingResponse` 监听 `http.disconnect`，断开后 `accepted.interrupt("client_disconnected")`，取消流任务。问答轮次失败码含 `client_disconnected`，并释放生成闸门。迟到断开不能覆盖已成功提交，也不能清掉新一轮闸门。

证据：`src/rag_backend/http/conversations.py`；`src/rag_backend/qa/answering.py` `AcceptedAnswer.interrupt`。

「节约 Token」是取消供应方流的设计意图；仓库没有测到的 token 用量数字。

### 引用必须落在本轮证据

受理后检索结果冻结为本轮证据。模型必须用 ASCII `[n]`，编号 ≤ 证据条数，残留方括号非法。正式回答正文、引用、助手 `completed` 同一事务提交。提交时对证据文档 `FOR SHARE`，集合对不上 → `evidence_invalidated`，正文不落库。当前索引指针切换不使已冻结证据失效；文档在提交前被删才会作废。

证据：`src/rag_backend/qa/answering.py` `selected_citation_numbers`、`SYSTEM_MESSAGE`；`src/rag_backend/qa/turns.py` `complete_evidence_turn`。

### 所有者隔离与生成闸门

知识库按拥有该库的用户划分可见性；其他用户与未知资源同一 `resource_not_found`。会话级生成闸门：`UPDATE ... generation_gate = true WHERE generation_gate = false`，并发第二问 409 `generation_in_progress`。

证据：`src/rag_backend/knowledge_bases/knowledge_bases.py`；`src/rag_backend/qa/turns.py` `accept_turn`。

### 处理任务投递（可讲，简历未单列）

生产投递是事务外至少一次 handoff：短事务读带令牌的待投递事实，提交后调 Procrastinate，再按状态+token 回写。接受重复 envelope，不在持锁时等调度器。

证据：`docs/adr/0002-at-least-once-processing-job-handoff.md`；`src/rag_backend/processing/handoff.py`；`src/rag_backend/processing/tasks.py`。

---

## 3. 已核对行为（测试名）

测试规模：`tests/` 下 `def test_` **139** 条（`rg` 计数，2026-09-18）。源码约 7205 行 / 测试约 8817 行。普通测试用 fake / 进程内 double；`scripts/smoke.py` 才打真实 Compose 服务。

| 口述主张 | 测试名 | 结果 |
|---|---|---|
| 热重建期间检索仍可用，且仍打旧当前索引 | `tests/processing/test_lifecycle.py` `test_reprocessing_keeps_old_index_then_atomically_replaces_or_retains_it` | 嵌入未完成时 `POST .../search` 返回 200，`current_index_build_id` 仍是旧构建；成功后原子替换；失败重建保留新指针 |
| 同一文档并发重建只接受一个活处理任务 | 同文件 `test_reprocessing_is_nested_and_concurrent_requests_accept_exactly_one` | 201 + 409 `active_job_exists`；部分唯一索引拒绝第二活任务 |
| 重复执行 / 旧 envelope 不能覆盖当前索引 | 同文件 `test_duplicate_execution_and_older_job_cannot_overwrite_current_index` | 新任务只发布一次；重放旧令牌不改指针 |
| 删除已提交后的迟到结果永不发布 | 同文件 `test_late_result_after_committed_deletion_never_publishes`；`tests/processing/test_execution_fencing.py` `test_parent_deletion_cancels_running_job_and_fences_late_publish` | 构建数 0，任务 cancelled / 不发布 |
| 发布持锁时，同知识库另一文档仍可入库 | `test_sibling_intake_proceeds_while_another_document_publishes` | 知识库 `FOR SHARE` 不堵兄弟文档 |
| 断开取消，释放生成闸门 | `tests/qa/test_answer_generation.py` `test_socket_disconnect_after_delta_releases_generation_gate` | 助手 `failed` / `client_disconnected`，无正文无引用，下一轮可受理 |
| 迟到断开不能覆盖成功或清新闸门 | 同文件 `test_late_disconnect_cannot_overwrite_success_or_clear_new_gate` | 已完成轮次保留；新一轮仍 generating |
| 虚假引用进不了库 | 同文件 `test_invalid_model_citations_fail_after_deltas_without_persisting_body`；`tests/qa/test_answering.py` `test_strict_citation_parser_rejects_missing_or_invalid_references` | 无引用、无正文、`invalid_answer`（`No citation` / `Bad [0]` / `Bad [2]` / `Bad [abc]`） |
| 引用按正文首次出现顺序落库 | `test_evidence_answer_stream_commits_backend_citations_in_first_mention_order` | `[2]` 先于 `[1]` |
| 本轮证据整集复核，即使模型只引一篇 | `test_full_evidence_set_is_rechecked_even_when_model_cites_only_one_document` | 未引用文档被删 → `evidence_invalidated` |
| 当前索引切换不推翻已冻结证据 | `test_current_index_pointer_switch_does_not_invalidate_frozen_evidence` | 生成中途改指针仍 `completed` |
| 引用插入失败回滚正式回答 | `test_citation_insert_failure_rolls_back_the_formal_answer_and_releases_gate` | 整笔回答不提交 |
| 同一会话同时只允许一轮 generating | `test_database_gate_allows_only_one_concurrent_generation` | 第二问 409 `generation_in_progress` |
| 迟到失败不能清新闸门 | `test_late_failure_cannot_clear_a_new_turn_generation_gate` | 旧轮 fail 不影响新轮 |
| Hybrid 双路融合 | `tests/search/test_hybrid_retrieval.py` `test_l2_injected_backends_drive_final_search_ranks` | 两路都贡献，RRF 排序 |
| 一路失败降级到另一路 | `test_d2c_one_leg_failure_falls_back_to_the_other` | dense 或 sparse 单独失败仍有命中 |
| 两路都失败不是空成功 | `test_d2c_both_legs_fail_is_search_unavailable_not_empty_success` | `SearchUnavailableError` |
| SQL 错误回滚到 Savepoint | `test_real_postgresql_leg_error_rolls_back_to_savepoint` | 失败路不污染事务 |
| 快照后指针切换，两路仍扫旧当前索引 | `test_pointer_switch_after_snapshot_keeps_both_legs_on_old_current_index` | 命中旧 excerpt |
| 嵌入阶段文档被删，第二阶段拒绝 | `tests/search/test_retrieval.py` `test_second_phase_rejects_a_document_deleted_during_embedding` | `SearchUnavailableError` |
| 非当前构建 / 空间不一致命中被拒 | `test_noncurrent_builds_and_incompatible_or_anomalous_hits_are_rejected` | 不得混扫 |
| MinIO 补偿删除 | `tests/documents/test_intake.py` `test_database_failure_after_object_write_attempts_compensating_delete` | DB 失败后 `deleted` 一次，503 `intake_unavailable` |
| 解析不堵事件循环 | `tests/index/test_source_derivation.py` `test_derive_sources_does_not_block_event_loop_while_parser_runs` | 解析阻塞时 loop 仍转 |
| 稀疏分词不堵事件循环 | `test_sparse_tokenization_does_not_block_the_event_loop` | jieba 在线程 |
| PDF 按物理页、不跨空页 | `tests/index/test_index_build.py` `test_pdf_chunks_preserve_physical_pages_and_never_cross_an_empty_page` | 页 1 与页 3 |
| 所有者与未知资源同一 404 | `tests/knowledge_bases/test_knowledge_bases.py` `test_other_user_and_unknown_knowledge_bases_have_identical_not_found_semantics`；`tests/search/test_retrieval.py` `test_http_search_stranger_and_unknown_kb_share_not_found_shape`；`tests/qa/test_conversations.py` `test_conversation_visibility_hides_owner_and_parent_mismatches` | 形状相同，不含「是否存在」 |
| 过期租约接管有上限 | `tests/processing/test_execution_fencing.py` `test_renewal_prevents_takeover_and_expired_lease_takeovers_stop_at_budget` | 心跳续约挡住接管；超预算终态 |

### 缺口（未在仓库找到）

- **「热重建期间问答保持可用」**：有检索可用性测试，有「指针切换不推翻本轮证据」测试，**没有**「发布事务持锁期间 `POST .../turns` 仍成功」的专项测试。口述应说「热重建期间检索仍可用；问答用冻结的本轮证据，不回读新指针」。
- **「外部向量 API 超时则熔断」**：有嵌入失败跳过密集路、一路 SQL 失败降级；**没有**专门的超时熔断器 / 半开状态测试。
- **「节约 Token」的量化**：有断开后关闭生成流（`test_closing_answer_generator_closes_underlying_openai_http_stream`、断开测试等 `answer_client.closed`）；**没有** token 计数。
- **自研 BM25 / 独立 AST 解析器 / MinIO Object Lock / exactly-once 投递**：未在仓库找到。
- **线上用户量、QPS、SLA、评测分数**：未在仓库找到。

---

## 4. 技术栈（仓库钉死的）

| 层 | 仓库事实 |
|---|---|
| 语言 | CPython 3.13（`pyproject.toml` `requires-python = ">=3.13,<3.14"`；`Dockerfile` `python:3.13.7-slim-bookworm`；ruff/pyright `py313`） |
| API | FastAPI + Uvicorn factory（`src/rag_backend/app.py`，`docker-compose.yml` `api`） |
| 业务库 | PostgreSQL 17 + pgvector 0.8.1（compose 镜像 `pgvector/pgvector:0.8.1-pg17`） |
| ORM / 驱动 | SQLAlchemy 2 asyncio + asyncpg；迁移 Alembic，单一基线 `0001_v1_baseline.py` |
| 原文对象 | MinIO（`quay.io/minio/minio:RELEASE.2025-04-22...`，bucket 默认 `rag-originals`） |
| 任务投递 | Procrastinate 3.x（`src/rag_backend/processing/tasks.py`，compose `worker`） |
| 嵌入 | DashScope `qwen3.7-text-embedding` 1024 维；嵌入空间字符串钉死在 `src/rag_backend/runtime/embeddings.py` `EMBEDDING_SPACE` |
| 回答 | OpenAI 兼容流式客户端，默认模型设置 `gpt-5.5`，本机 `ANSWER_BASE_URL=http://127.0.0.1:8317/v1` |
| 词法 | jieba + PostgreSQL `simple` FTS |
| 解析 | `markdown-it-py==3.0.0`，`pypdf==6.14.2` |
| 认证 | 邮箱用户 + 不透明会话凭据 + Argon2id |
| 运行 | Docker Compose `portfolio-rag`；API/worker `network_mode: host`，只监听回环 |
| 门禁 | ruff / pyright strict / pytest；`uv sync --frozen --group dev` |

简历 tech 行 `FastAPI, PostgreSQL, pgvector, SQLAlchemy, MinIO, Docker` 仍被代码支持。可补一句 Procrastinate，但不要把 Compose 本地 worker 说成生产任务集群。

---

## 5. 个人角色与规模

- 角色：独立个人项目。git log 16 次提交，作者仅 `ARKL5 <389932458@qq.com>`。README / AGENTS 写明本科实习 / 求职作品集。
- 简历项目名「用户隔离的高可靠 RAG 知识库后端」、时间 `2026.06–2026.08`、GitHub `ARKL5/rag-backend`。公开 git 快照始于 **2026-08-28**（`Initial public snapshot of the RAG backend portfolio.`）。**开始月份未在仓库找到独立证明**；不要把 6 月开工说成 git 证据。
- 规模可讲：源码约 7.2k 行、测试约 8.8k 行、139 条测试、4 份 ADR、单一 Alembic 基线。不要编用户量、部署实例数、日活。
- 支持格式：txt / md / pdf；文档上限 20 MiB；PDF 页上限 500；切块上限 1000。

---

## 6. 面试官追问：仓库能答 / 不能答

### 能答（带路径）

- 为什么 PostgreSQL 是事务核心、MinIO 只存原文？→ ADR-0001，`indexing.py` `_publish`，`object_store.py`。
- 为什么至少一次而不是 exactly-once？→ ADR-0002，`handoff.py`，token fencing。
- 锁序如何避免死锁、又允许同库不同文档并发发布？→ ADR-0003，`test_sibling_intake_proceeds_while_another_document_publishes`。
- 过期执行如何不覆盖新当前索引？→ ADR-0004，`execution.py` `_complete_success`，lifecycle 测试。
- 检索为何 REPEATABLE READ + Savepoint？→ `retrieval.py`；hybrid 测试。
- 为什么引用不跟「当前文本片段」活关系？→ `CONTEXT.md` 本轮证据 / 引用；`complete_evidence_turn` 写快照。
- 所有者隔离如何避免存在性泄漏？→ 知识库 / 检索 / 会话测试的同一 404。
- 生成闸门与断开取消如何收敛？→ `turns.py` `generation_gate`；SSE disconnect 测试。
- 为什么默认不能改成 0.0.0.0？→ README「超出可信本机 V1 的支持边界」。

### 不能答（未在仓库找到，不要临场编）

- 线上 QPS、P99、可用性、用户数、成本。
- 公网暴露、鉴权网关、CDN、K8s 生产拓扑。
- 多租户、成员、RBAC、共享知识库。
- 自研检索引擎、学习 to-rank、商业向量库对比评测。
- DashScope / 回答模型的准确率、幻觉率、token 账单。
- MinIO 服务端 WORM、跨 AZ 复制。
- 「我在公司里把这套上了生产」。

---

## 7. 建议写进口述的 6 条 bullet

每条 ≤80 字，可被代码/测试核对。

1. 知识库 FOR SHARE、文档/任务/索引 FOR UPDATE 固定锁序；同一事务写入切块并切换当前索引，热重建时检索仍扫旧指针。  
   证据：`src/rag_backend/index/indexing.py` `_publish`；`tests/processing/test_lifecycle.py` `test_reprocessing_keeps_old_index_then_atomically_replaces_or_retains_it`

2. 发布按执行令牌条件写入；活任务必须持 token、终态清空，迟到结果与旧 envelope 不能覆盖当前索引。  
   证据：`src/rag_backend/processing/execution.py` `_complete_success`；`tests/processing/test_lifecycle.py` `test_duplicate_execution_and_older_job_cannot_overwrite_current_index`

3. REPEATABLE READ 固定当次当前索引；密集/稀疏两路各进 Savepoint，一路失败降级，双路用 RRF（k=60）融合。  
   证据：`src/rag_backend/search/retrieval.py`；`src/rag_backend/search/fusion.py`；`tests/search/test_hybrid_retrieval.py` `test_d2c_one_leg_failure_falls_back_to_the_other`、`test_real_postgresql_leg_error_rolls_back_to_savepoint`

4. MinIO 先存原文，数据库事务失败后补偿删除；解析进线程池，Markdown 保留标题路径，PDF 按物理页切。  
   证据：`src/rag_backend/documents/documents.py` `accept`；`src/rag_backend/runtime/object_store.py`；`src/rag_backend/index/text_sources.py`；`tests/documents/test_intake.py` `test_database_failure_after_object_write_attempts_compensating_delete`

5. SSE 监听到 http.disconnect 即取消生成，问答轮次记 client_disconnected 并释放生成闸门。  
   证据：`src/rag_backend/http/conversations.py` `_DisconnectSupervisedStreamingResponse`；`tests/qa/test_answer_generation.py` `test_socket_disconnect_after_delta_releases_generation_gate`

6. 引用必须落在本轮证据：越界编号不落库；提交时 FOR SHARE 复核证据文档仍有效。  
   证据：`src/rag_backend/qa/answering.py` `selected_citation_numbers`；`src/rag_backend/qa/turns.py` `complete_evidence_turn`；`tests/qa/test_answer_generation.py` `test_invalid_model_citations_fail_after_deltas_without_persisting_body`

---

## 8. 明确禁止的夸大

- 禁止说成公网 SaaS、云服务、生产平台、高可用集群、已服务真实用户。
- 禁止说「多租户 / 租户隔离 / RBAC」。仓库是**所有者隔离**。
- 禁止把执行令牌 fencing 说成完整教科书「乐观并发控制」；禁止把 Savepoint 降级说成熔断器。
- 禁止把 jieba + PG `simple` FTS 说成自研 BM25。
- 禁止把 markdown-it token 说成 AST 引擎。
- 禁止把 MinIO 应用层不可变说成 Object Lock / WORM。
- 禁止把 at-least-once + fencing 说成 exactly-once。
- 禁止「热重建期间问答保持可用」而不加限定；只证明了检索可用 + 本轮证据冻结。
- 禁止「断开取消节约了 X Token」——无计量。
- 禁止编用户量、QPS、准确率、上线业绩。
- 禁止把本机 DashScope / `127.0.0.1:8317` 回答供应方说成自研大模型。
- 禁止把作品集后端的「高可靠」理解成 SLA；仓库证明的是并发下的收敛与隔离，不是运营可靠性。

---

## 简历四条逐条核对（`resume/resume-data-agent.json`）

项目条现标题「用户隔离的高可靠 RAG 知识库后端」。四条 `evidence_type: repository_verified`。校园简历 `resume-data-campus.json` 同文。

1. **锁序 + 原子切换 + 热重建检索 + 过期任务不覆盖**  
   主体仍被代码支持。用词修正：「乐观并发控制」改为「执行令牌 fencing」；「检索问答保持可用」改为「检索保持可用」。`source_note` 指向 `indexing.py _publish`、`test_lifecycle.py` 仍准。

2. **REPEATABLE READ + Hybrid + Savepoint + RRF k=60**  
   仍被支持。用词修正：不要说「超时熔断」；说「嵌入或一路失败则降级，双路失败返回 search_unavailable」。`source_note` 指向 `retrieval.py`、`fusion.py` 仍准。

3. **MinIO 补偿 + Markdown 标题路径 + PDF 物理页 + 线程池解析**  
   仍被支持。用词修正：「AST」改为「markdown-it 标题 token / 标题层级路径」。标点边界回退在 `_chunk_end`，不仅 PDF。`source_note` 指向 `text_sources.py`、`documents.py` 仍准。

4. **SSE 断开取消 + 行锁校验引用文档 + 拒绝编造引用**  
   仍被支持。断开取消与虚假引用不落库有测试。「节约 Token」只可作动机，不可当结果。「可回溯到真实文档」更准确是：引用是本轮证据快照，提交时文档仍须存在；不是跟当前索引活绑。`source_note` 指向 `http/conversations.py`、`qa/turns.py` 仍准。

结论：四条机制都还在树上，没有过期到「不能再讲」。需要改的是行业词包装（OCC、熔断、AST、SaaS 可靠性），不是删项目。
