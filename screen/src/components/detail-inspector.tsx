import { memo, useMemo, useState } from "react"
import { itemReason } from "../reason"
import { bossHref, jobKey, type ScreenItem } from "../types"

type Props = {
  item: ScreenItem | null
  isStarred: boolean
  onToggleStar: (key: string) => void
  stationTitle: string
  laneTitle?: string
}

function activeClass(text?: string): string {
  if (!text) return "act-none"
  if (/刚刚|在线|今日|今天|[123]日|[123]天/.test(text)) return "act-hot"
  if (/本周|周内|[4567]日|[4567]天|2周/.test(text)) return "act-mid"
  return "act-cold"
}

// 关键词高亮渲染器
const TECH_KEYWORDS = [
  "retail-bench",
  "rag-backend",
  "tau2-bench",
  "Agent开发",
  "Agent",
  "智能体",
  "RAG",
  "LLM",
  "大模型",
  "Tool Calling",
  "两阶段提交",
  "确定性评测",
  "混合检索",
  "异步锁序",
  "知识库",
  "FastAPI",
  "PostgreSQL",
  "pgvector",
  "LangGraph",
  "LangChain",
  "Python",
  "Pydantic",
  "pytest",
  "全栈",
]

function highlightTechKeywords(text: string) {
  if (!text) return text
  const escaped = TECH_KEYWORDS.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
  const regex = new RegExp(`(${escaped.join("|")})`, "gi")
  const parts = text.split(regex)

  return parts.map((part, i) => {
    const isMatched = TECH_KEYWORDS.some((k) => k.toLowerCase() === part.toLowerCase())
    if (isMatched) {
      return (
        <mark key={i} className="tech-badge">
          {part}
        </mark>
      )
    }
    return part
  })
}

function FormattedJd({ text }: { text: string }) {
  const rendered = useMemo(() => {
    const lines = text.split(/\r?\n/)
    return lines.map((line, idx) => {
      const trimmed = line.trim()
      if (!trimmed) {
        return <div key={idx} className="jd-spacer" />
      }

      // 匹配章节标题
      const isHeader =
        /^(?:岗位职责|工作职责|工作内容|职位职责|岗位要求|任职要求|任职资格|任职条件|我们需要你|加分项)[：:]?\s*$/i.test(
          trimmed,
        ) ||
        /^【(?:岗位职责|任职要求|任职资格|工作职责)】/.test(trimmed)

      if (isHeader) {
        return (
          <div key={idx} className="jd-section-header">
            <span className="jd-section-bar" />
            <span className="jd-section-title">{trimmed}</span>
          </div>
        )
      }

      return (
        <div key={idx} className="jd-line">
          {highlightTechKeywords(line)}
        </div>
      )
    })
  }, [text])

  return <div className="formatted-jd">{rendered}</div>
}

function DetailInspector({ item, isStarred, onToggleStar, stationTitle, laneTitle }: Props) {
  const [copied, setCopied] = useState(false)

  if (!item) {
    return (
      <main className="detail-inspector is-empty">
        <div className="inspector-placeholder">
          <div className="placeholder-icon">👈</div>
          <div className="placeholder-title">选择一个岗位开始决策</div>
          <div className="placeholder-desc">使用鼠标点击左侧卡片，或使用键盘 j / k 上下浏览</div>
        </div>
      </main>
    )
  }

  const key = jobKey(item)
  const href = bossHref(item.href)
  const jobName = item.job || "（无岗位名）"
  const company = item.company || "（无公司名）"
  const area = item.area?.trim()
  const salary = item.salary?.trim()
  const activeText = item.active?.trim()
  const recruiter = item.recruiter?.trim()
  const hasJd = Boolean(item.hasJd || (item.jd && String(item.jd).trim()))
  const reason = itemReason(item)
  const actCls = activeClass(activeText)

  const isRiskClean = reason.modular?.risk?.includes("无明显硬伤")

  const onCopySummary = () => {
    const bench = reason.modular?.benchmark || reason.summarySnippet || ""
    const text = `[${company}] ${jobName} | 薪资: ${salary || "面议"} | 地点: ${area || "未知"} | 对标: ${bench}`
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <main className="detail-inspector">
      <div className="inspector-scroll-area">
        {/* 顶部头部看板 */}
        <header className="inspector-header">
          <div className="header-top-row">
            <div className="header-title-group">
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noreferrer"
                  className="header-job-title"
                  title="在新标签页打开 Boss 原网页 (Enter)"
                >
                  <span>{jobName}</span>
                  <span className="ext-icon">↗</span>
                </a>
              ) : (
                <h1 className="header-job-title plain">{jobName}</h1>
              )}
            </div>

            <div className="header-actions">
              <button
                type="button"
                className={`action-btn action-copy-btn ${copied ? "is-copied" : ""}`}
                onClick={onCopySummary}
                title="复制核心对标信息到剪贴板"
              >
                {copied ? "已复制 ✓" : "复制对标摘要"}
              </button>

              <button
                type="button"
                className={`action-btn action-star-btn ${isStarred ? "is-on" : ""}`}
                onClick={() => onToggleStar(key)}
              >
                <span className="star-dot">{isStarred ? "●" : "○"}</span>
                <span>{isStarred ? "已圈岗" : "圈岗"}</span>
                <kbd className="btn-kbd">s</kbd>
              </button>

              {href ? (
                <a href={href} target="_blank" rel="noreferrer" className="action-btn action-boss-btn">
                  <span>在 Boss 打开</span>
                  <span className="btn-icon">↗</span>
                  <kbd className="btn-kbd on-dark">Enter</kbd>
                </a>
              ) : null}
            </div>
          </div>

          <div className="header-meta-row">
            <span className="meta-company">{company}</span>
            {area ? <span className="meta-tag meta-area">📍 {area}</span> : null}
            {salary ? <span className="meta-tag meta-salary">💰 {salary}</span> : null}
            {recruiter ? <span className="meta-tag meta-recruiter">👤 {recruiter}</span> : null}
            {activeText ? (
              <span className={`meta-active-badge ${actCls}`}>
                <span className="pulse-dot" />
                {activeText}
              </span>
            ) : null}
          </div>

          {item.keywords && item.keywords.length > 0 ? (
            <div className="header-keywords-row">
              <span className="kw-label">命中搜词：</span>
              <div className="kw-chips">
                {item.keywords.map((kw) => (
                  <span key={kw} className="kw-chip">
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </header>

        {/* AI 决策评语区 (Dossier Briefing) */}
        <section className="inspector-section section-decision">
          <div className="section-header">
            <div className="section-title-wrap">
              <div className="section-title-badge">AI</div>
              <h2 className="section-title">智能决策情报卷宗</h2>
              <span className={`stage-indicator tone-${stationTitle}`}>
                {stationTitle}
              </span>
              {laneTitle ? <span className="lane-indicator">{laneTitle}</span> : null}
            </div>
            {reason.note ? <span className="note-badge">⚠️ {reason.note}</span> : null}
          </div>

          <div className="section-body">
            {reason.modular ? (
              <div className="modular-dossier">
                {/* 1. 职责与场景 */}
                <div className="dossier-card dossier-duty">
                  <div className="card-header">
                    <span className="card-eyebrow">MISSION / 业务与场景</span>
                    <span className="card-badge">职责拆解</span>
                  </div>
                  <div className="card-content">{reason.modular.dutyAndTech}</div>
                </div>

                {/* 2. 核心对标点 - 最高优先级视觉 */}
                <div className="dossier-card dossier-benchmark">
                  <div className="card-header">
                    <span className="card-eyebrow">LEVERAGE / 核心对标与切入点</span>
                    <span className="card-badge is-highlight">高契合度穿透</span>
                  </div>
                  <div className="card-content benchmark-text">
                    {highlightTechKeywords(reason.modular.benchmark)}
                  </div>
                </div>

                {/* 3. 公司背景 */}
                <div className="dossier-card dossier-company">
                  <div className="card-header">
                    <span className="card-eyebrow">COMPANY / 企业背景</span>
                    <span className="card-badge">规模与融资</span>
                  </div>
                  <div className="card-content">
                    {reason.modular.companyBg || "未标明具体融资或规模信息"}
                  </div>
                </div>

                {/* 4. 排雷风险 */}
                <div className={`dossier-card dossier-risk ${isRiskClean ? "is-clean" : "is-warning"}`}>
                  <div className="card-header">
                    <span className="card-eyebrow">TRIAGE / 排雷风险</span>
                    <span className={`card-badge ${isRiskClean ? "is-safe" : "is-risk"}`}>
                      {isRiskClean ? "安全通关" : "注意门槛"}
                    </span>
                  </div>
                  <div className="card-content">{reason.modular.risk}</div>
                </div>
              </div>
            ) : reason.dropCategory ? (
              <div className="drop-dossier">
                <div className="drop-header">
                  <span className="drop-tag">【{reason.dropCategory}】</span>
                  <span className="drop-title">淘汰判定证据</span>
                </div>
                <div className="drop-evidence">{reason.dropEvidence || reason.body}</div>
              </div>
            ) : (
              <div className="generic-reason-card">
                <div className="generic-reason-header">
                  {reason.kind ? <span className="kind-pill">{reason.kind}</span> : null}
                  {reason.phase ? <span className="phase-pill">{reason.phase}</span> : null}
                </div>
                <div className="generic-reason-body">{reason.body}</div>
              </div>
            )}
          </div>
        </section>

        {/* 原始 JD 对照区 */}
        <section className="inspector-section section-jd">
          <div className="section-header">
            <div className="section-title-wrap">
              <div className="section-title-badge jd-badge">JD</div>
              <h2 className="section-title">原始岗位职责与任职要求</h2>
            </div>
            <span className={`jd-status-badge ${hasJd ? "is-present" : "is-missing"}`}>
              {hasJd ? "已获取全文" : "初筛阶段无详情"}
            </span>
          </div>

          <div className="section-body">
            {hasJd ? (
              <div className="jd-text-wrapper">
                <FormattedJd text={item.jd || ""} />
              </div>
            ) : (
              <div className="jd-missing-notice">
                <div className="notice-icon">📭</div>
                <div className="notice-text">
                  本岗位停留在初筛阶段，未抓取详情 JD
                </div>
                <div className="notice-sub">
                  流水线停驻：<strong>{stationTitle}</strong>
                  {laneTitle ? ` · 分类：${laneTitle}` : ""}
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}

export default memo(DetailInspector)
