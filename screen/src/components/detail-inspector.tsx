import { memo } from "react"
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

function DetailInspector({ item, isStarred, onToggleStar, stationTitle, laneTitle }: Props) {
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
                  {jobName}
                  <span className="ext-icon">↗</span>
                </a>
              ) : (
                <h1 className="header-job-title plain">{jobName}</h1>
              )}
            </div>

            <div className="header-actions">
              <button
                type="button"
                className={`action-star-btn ${isStarred ? "is-on" : ""}`}
                onClick={() => onToggleStar(key)}
              >
                {isStarred ? "● 已圈岗 (s)" : "○ 圈岗 (s)"}
              </button>
              {href ? (
                <a href={href} target="_blank" rel="noreferrer" className="action-boss-btn">
                  在 Boss 打开 ↗
                </a>
              ) : null}
            </div>
          </div>

          <div className="header-meta-row">
            <span className="meta-company">{company}</span>
            {area ? <span className="meta-area">{area}</span> : null}
            {salary ? <span className="meta-salary">{salary}</span> : null}
            {recruiter ? <span className="meta-recruiter">招聘者：{recruiter}</span> : null}
            {activeText ? (
              <span className={`meta-active-badge ${actCls}`}>
                {activeText}
              </span>
            ) : null}
          </div>

          {item.keywords && item.keywords.length > 0 ? (
            <div className="header-keywords-row">
              <span className="kw-label">命中搜词：</span>
              {item.keywords.map((kw) => (
                <span key={kw} className="kw-tag">
                  {kw}
                </span>
              ))}
            </div>
          ) : null}
        </header>

        {/* AI 决策与对标评语区 (Hero Section) */}
        <section className="inspector-section section-decision">
          <div className="section-header">
            <div className="section-title-wrap">
              <span className="section-icon">🧠</span>
              <h2 className="section-title">AI 决策评语</h2>
              <span className="stage-badge">{stationTitle}</span>
              {laneTitle ? <span className="lane-badge">{laneTitle}</span> : null}
            </div>
            {reason.note ? <span className="note-badge">{reason.note}</span> : null}
          </div>

          <div className="section-body">
            {reason.modular ? (
              <div className="modular-dossier">
                <div className="dossier-card dossier-duty">
                  <div className="card-label">
                    <span className="label-icon">🎯</span> 职责与业务场景
                  </div>
                  <div className="card-content">{reason.modular.dutyAndTech}</div>
                </div>

                <div className="dossier-card dossier-benchmark">
                  <div className="card-label">
                    <span className="label-icon">⚡</span> 核心对标与技术切入点
                  </div>
                  <div className="card-content">{reason.modular.benchmark}</div>
                </div>

                <div className="dossier-card dossier-company">
                  <div className="card-label">
                    <span className="label-icon">🏢</span> 公司背景与融资规模
                  </div>
                  <div className="card-content">{reason.modular.companyBg || "未标明融资或规模"}</div>
                </div>

                <div className={`dossier-card dossier-risk ${isRiskClean ? "is-clean" : "is-warning"}`}>
                  <div className="card-label">
                    <span className="label-icon">{isRiskClean ? "🛡️" : "⚠️"}</span> 排雷与潜在风险
                  </div>
                  <div className="card-content">{reason.modular.risk}</div>
                </div>
              </div>
            ) : reason.dropCategory ? (
              <div className="drop-dossier">
                <div className="drop-header">
                  <span className="drop-tag">【{reason.dropCategory}】</span>
                  <span className="drop-title">淘汰判定依据</span>
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
              <span className="section-icon">📄</span>
              <h2 className="section-title">原始岗位职责与任职要求 (JD)</h2>
            </div>
            <span className={`jd-status-badge ${hasJd ? "is-present" : "is-missing"}`}>
              {hasJd ? "已获取全文" : "初筛阶段无详情"}
            </span>
          </div>

          <div className="section-body">
            {hasJd ? (
              <div className="jd-text-wrapper">
                <pre className="jd-text">{item.jd}</pre>
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
