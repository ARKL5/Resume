---
name: boss-ops
description: 值守或排障 Boss 筛选运行时使用：启动并盯完一轮筛选、处理风控暂停或连续失败、或在修改 boss.yaml 后抽检与回拨 boss.db 重评。
---

# Boss 筛选值守与运维

本仓库的筛选进程是长时本机任务（单轮可持续数小时）。通过 `--watch` 将后台浏览器进程与前台事件值守解耦，实现零轮询消耗盯完全程。

## 值守循环

1. **启动或续守**：从仓库根执行 `uv run python src/boss_screen/__main__.py --watch`（不设短超时）。
   - 未运行时自动以独立会话后台拉起筛选进程并写入 `.boss-screen.lock`；已运行时直接从当前日志末尾挂接。
   - 正常筛岗、翻页与冷却期间保持静默阻塞，仅输出收获卡片、保留岗与关键词汇总。
2. **按返回码处置**：
   - **退出码 `0`（`值守结束：筛选进程已退出`）**：全城全词已跑完。查询 `boss.db` 统计本轮各 `stage` 数量及新增 `ai_keep` 岗位并汇报。
   - **退出码 `2`（异常唤醒）**：后台筛选进程与 Chrome 仍保持现场（除触发停机熔断外）。按下方「现场排障」处置；恢复后再次执行 `--watch` 续守，直至退出码为 `0`。

完成标准：`--watch` 以退出码 `0` 跑完所有城市与关键词并输出统计汇报，或定位到需人工介入的阻塞点并附现场信息通知用户。

## 现场排障

筛选进程将 Chrome 开在本机 `9222` 端口。排查期间使用 `agent-browser --cdp 9222` 只读查看（`tab list`、`snapshot -i`、`screenshot`），保持筛选进程对页面的会话控制。

- **`暂停等人`（`onRisk: wait` 停在人机验证或登录页）**
  1. 执行 `agent-browser --cdp 9222 tab list` 定位页面，用 `screenshot` 或 `snapshot -i` 确认验证类型。
  2. 通知用户完成滑块或登录；用户处理后筛选进程在 5 秒内自动识别 `验证已消失，继续`，此时再次运行 `--watch` 续守。
- **`停止本轮筛选`（连续失败熔断，进程已收尾退出）**
  - **AI 连续 3 次失败**：检查 `boss.yaml` 中 `ai.baseUrl` 服务连通性；恢复后再次运行 `--watch`（库内已抓正文的待评记录会在启动时零网页点击优先补评）。
  - **详情跨关键词连续 3 次失败**：核对 `src/boss_screen/cards.py` 的 `parse_detail` 与列表选择器是否因页面改版失效；若属平台接口限流，汇报用户暂停运行。
- **`值守告警`（日志连续 300 秒无更新）**
  1. 用 `agent-browser --cdp 9222 tab list` 与 `snapshot -i` 检查页面是否卡在未识别弹窗。
  2. 需重启时，向运行进程发送 `SIGINT`：`kill -INT $(cat .boss-screen.lock)`，等待进程释放锁并干净关闭 Chrome 后，再执行 `--watch` 拉起。

## 调优与回拨重评

用户修改 `boss.yaml`（关键词、黑名单、规则词、候选人画像或 Prompt）后：

1. **抽检停因**：`boss.db` 为 WAL 模式，可在运行期直接并发查询各 `stage` 的 `company, job, reason` 复盘误杀或漏杀。
2. **回拨状态（仅使用 `src/boss_screen/rules.py` 中 `PLACED_STAGES` 定义的合法值）**：
   - **零点击重评 JD**：对已有正文的记录（`trim(jd) != ''`），将 `stage` 更新为 `'ai_jd_pending'`。下次启动时 `_retry_pending_jds()` 会在打开网页前直接后台重评。
   - **重评标题初筛**：将无正文的被淘汰/含糊记录 `stage` 更新为 `'ai_title_pending'`，下次列表刷到时重新调用标题 AI。
3. **重启生效**：`boss.yaml` 在启动时加载。若筛选进程在跑，执行 `kill -INT $(cat .boss-screen.lock)` 等待收尾退出，再执行 `--watch` 启动新配置。

完成标准：`boss.db` 目标记录已更新为合法待评状态，且新配置已通过重启筛选进程生效。
