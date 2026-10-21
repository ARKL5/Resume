import { memo, useMemo, useState } from "react"
import { itemReason } from "../reason"
import { activeClass, batchKey, batchLabel, batchMoment, bossHref, jobKey, type ScreenItem } from "../types"

type Props = {
  item: ScreenItem | null
  isStarred: boolean
  onToggleStar: (key: string) => void
  stationTitle: string
  laneTitle?: string
}

function FormattedJd({ text }: { text: string }) {
  const rendered = useMemo(() => {
    const lines = text.split(/\r?\n/)
    return lines.map((line, idx) => {
      const trimmed = line.trim()
      if (!trimmed) {
        return <div key={idx} className="jd-spacer" />
      }

      const isMdHeader = /^#+\s+(.+)$/.exec(trimmed)
      const isNamedHeader =
        /^(?:岗位职责|工作职责|工作内容|职位职责|岗位要求|任职要求|任职资格|任职条件|我们需要你|加分项|职位描述|技术栈|你将获得)[：:]?\s*$/i.test(
          trimmed,
        ) ||
        /^【(?:岗位职责|任职要求|任职资格|工作职责|职位描述|技术栈|任职条件)】/.test(trimmed)

      if (isMdHeader || isNamedHeader) {
        const headerTitle = isMdHeader ? isMdHeader[1] : trimmed
        return (
          <div key={idx} className="swiss-jd-header">
            <span className="header-title">{headerTitle}</span>
          </div>
        )
      }

      return (
        <div key={idx} className="swiss-jd-line">{line}</div>
      )
    })
  }, [text])

  return <div className="swiss-formatted-jd">{rendered}</div>
}

function DetailInspector({ item, isStarred, onToggleStar, stationTitle, laneTitle }: Props) {
  const [copied, setCopied] = useState(false)

  if (!item) {
    return (
      <main className="detail-inspector is-empty">
        <div className="swiss-placeholder">
          <div className="placeholder-mark">无选中</div>
          <div className="placeholder-sub">请在左侧列表按 j / k 选择岗位开始审阅</div>
        </div>
      </main>
    )
  }

  const key = jobKey(item)
  const href = bossHref(item.href)
  const jobName = item.job || "（未命名岗位）"
  const company = item.company || "（未标明公司）"
  const area = item.area.trim()
  const salary = item.salary?.trim()
  const activeText = item.active.trim()
  const recruiter = [item.recruiter?.trim(), item.recruiterTitle?.trim()].filter(Boolean).join(" · ")
  const companyFacts = [item.industry?.trim(), item.scale?.trim(), item.financing?.trim()].filter(Boolean).join(" / ")
  const reqFacts = [item.degree?.trim(), item.experience?.trim()].filter(Boolean).join(" · ")
  const hasJd = Boolean(item.jd?.trim())
  const reason = itemReason(item)
  const actCls = activeClass(activeText)
  const batch = batchLabel(batchKey(item.batchAt))
  const batchMomentText = batchMoment(item.batchAt)

  const isRiskClean = reason.modular?.risk?.includes("无明显硬伤")

  const onCopySummary = () => {
    const bench = reason.modular?.benchmark || reason.summarySnippet || ""
    const text = `[${company}] ${jobName} | 薪资: ${salary || "面议"} | 地点: ${area || "未知"} | 对标: ${bench}`
    navigator.clipboard
      ?.writeText(text)
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      })
      .catch(() => {
        /* ignore or fallback */
      })
  }

  return (
    <main className="detail-inspector">
      <div className="inspector-scroll-area">
        {/* 瑞士版式头部看板 */}
        <header className="swiss-header">
          <div className="header-top-row">
            <div className="header-title-wrap">
              {href ? (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="swiss-job-title"
                  title="在 Boss 直聘打开原始页面 (Enter)"
                >
                  {jobName}
                  <span className="arrow-icon">↗</span>
                </a>
              ) : (
                <h1 className="swiss-job-title">{jobName}</h1>
              )}
            </div>

            <div className="header-actions">
              <button
                type="button"
                className={`swiss-btn ${copied ? "is-active" : ""}`}
                onClick={onCopySummary}
              >
                {copied ? "已复制 ✓" : "复制对标摘要"}
              </button>

              <button
                type="button"
                className={`swiss-btn ${isStarred ? "is-starred" : ""}`}
                onClick={() => onToggleStar(key)}
              >
                <span>{isStarred ? "★ 已圈岗" : "☆ 圈岗"}</span>
                <span className="key-tag">s</span>
              </button>

              {href ? (
                <a href={href} target="_blank" rel="noopener noreferrer" className="swiss-btn is-primary">
                  <span>在 BOSS 打开</span>
                  <span className="key-tag on-dark">Enter</span>
                </a>
              ) : null}
            </div>
          </div>

          <div className="swiss-meta-bar">
            <span className="meta-block company-block">{company}</span>
            {companyFacts ? <span className="meta-block area-block">{companyFacts}</span> : null}
            {area ? <span className="meta-block area-block">{area}</span> : null}
            {salary ? <span className="meta-block salary-block">{salary}</span> : null}
            {reqFacts ? <span className="meta-block area-block">{reqFacts}</span> : null}
            {recruiter ? <span className="meta-block recruiter-block">{recruiter}</span> : null}
            {activeText ? (
              <span className={`meta-block active-block ${actCls}`}>{activeText}</span>
            ) : null}
            {batch ? (
              <span className="meta-block batch-block" title={`筛选批次：${batchMomentText}`}>
                批次 {batchMomentText || batch}
              </span>
            ) : null}
          </div>

          {item.keywords.length > 0 ? (
            <div className="swiss-keywords-bar">
              {item.keywords.map((kw) => (
                <span key={kw} className="swiss-kw-chip">
                  {kw}
                </span>
              ))}
            </div>
          ) : null}
        </header>

        {/* 瑞士网格决策卷宗 */}
        <section className="swiss-section">
          <div className="section-masthead">
            <div className="masthead-left">
              <h2 className="section-label">AI 决策研判卷宗</h2>
            </div>
            <div className="masthead-right">
              <span className="masthead-tag status-tag">{stationTitle}</span>
              {laneTitle ? <span className="masthead-tag lane-tag">{laneTitle}</span> : null}
            </div>
          </div>

          <div className="section-content">
            {reason.modular ? (
              <div className="swiss-grid-dossier">
                {/* 01 职责与业务 */}
                <div className="dossier-row row-duty">
                  <div className="row-prefix">
                    <span className="row-title">职责与技术场景</span>
                  </div>
                  <div className="row-body">{reason.modular.dutyAndTech}</div>
                </div>

                <div className="dossier-row row-benchmark">
                  <div className="row-prefix">
                    <span className="row-title">对标与切入点</span>
                  </div>
                  <div className="row-body benchmark-content">{reason.modular.benchmark}</div>
                </div>

                <div className="dossier-row row-company">
                  <div className="row-prefix">
                    <span className="row-title">企业规模与融资</span>
                  </div>
                  <div className="row-body">
                    {reason.modular.companyBg || "未标明融资或规模细节"}
                  </div>
                </div>

                <div className={`dossier-row row-risk ${isRiskClean ? "is-clean" : "is-warning"}`}>
                  <div className="row-prefix">
                    <span className="row-title">排雷研判与风险</span>
                  </div>
                  <div className="row-body risk-content">{reason.modular.risk || "未提供风险评语"}</div>
                </div>
              </div>
            ) : reason.dropCategory ? (
              <div className="swiss-drop-box">
                <div className="drop-banner">
                  <span className="drop-category">【{reason.dropCategory}】</span>
                </div>
                <div className="drop-evidence-text">{reason.dropEvidence || reason.body}</div>
              </div>
            ) : (
              <div className="swiss-generic-box">
                <div className="generic-body">{reason.body}</div>
              </div>
            )}
          </div>
        </section>

        {/* 瑞士纯粹 JD 原文阅读区 */}
        <section className="swiss-section">
          <div className="section-masthead">
            <div className="masthead-left">
              <h2 className="section-label">原始岗位职责与任职要求 (JD)</h2>
            </div>
            <div className="masthead-right">
              <span className={`masthead-tag ${hasJd ? "jd-ready" : "jd-missing"}`}>
                {hasJd ? "已拉取" : "粗筛未抓取"}
              </span>
            </div>
          </div>

          <div className="section-content jd-content-box">
            {hasJd ? (
              <FormattedJd text={item.jd || ""} />
            ) : (
              <div className="swiss-missing-notice">
                <div className="notice-text">
                  本岗位在列表标题粗筛阶段停驻，未发起详情页抓取请求
                </div>
                <div className="notice-path">
                  当前停驻：{stationTitle}
                  {laneTitle ? `，分类：${laneTitle}` : ""}
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
