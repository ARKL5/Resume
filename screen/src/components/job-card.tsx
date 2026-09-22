import { memo, useEffect, useRef } from "react"
import { itemReason } from "../reason"
import { jobKey, type ScreenItem } from "../types"

type Props = {
  item: ScreenItem
  isSelected: boolean
  isStarred: boolean
  onSelect: () => void
  onToggleStar: (key: string) => void
}

function activeClass(text?: string): string {
  if (!text) return "act-none"
  if (/刚刚|在线|今日|今天|[123]日|[123]天/.test(text)) return "act-hot"
  if (/本周|周内|[4567]日|[4567]天|2周/.test(text)) return "act-mid"
  return "act-cold"
}

function JobCard({ item, isSelected, isStarred, onSelect, onToggleStar }: Props) {
  const cardRef = useRef<HTMLDivElement>(null)
  const key = jobKey(item)
  const jobName = item.job || "（无岗位名）"
  const company = item.company || "（无公司名）"
  const area = item.area?.trim()
  const salary = item.salary?.trim()
  const activeText = item.active?.trim()
  const reason = itemReason(item)
  const actCls = activeClass(activeText)

  useEffect(() => {
    if (isSelected && cardRef.current) {
      cardRef.current.scrollIntoView({ block: "nearest", behavior: "smooth" })
    }
  }, [isSelected])

  return (
    <div
      ref={cardRef}
      onClick={onSelect}
      className={`job-card ${isSelected ? "is-selected" : ""} ${isStarred ? "is-starred" : ""}`}
    >
      <div className="card-left">
        <button
          type="button"
          className={`star-btn ${isStarred ? "is-on" : ""}`}
          onClick={(e) => {
            e.stopPropagation()
            onToggleStar(key)
          }}
          title={isStarred ? "取消圈岗 (s)" : "圈岗 (s)"}
          aria-label={isStarred ? "取消圈岗" : "圈岗"}
        >
          {isStarred ? "●" : "○"}
        </button>
      </div>

      <div className="card-main">
        <div className="card-row1">
          <span className="card-title" title={jobName}>
            {jobName}
          </span>
          {salary ? <span className="card-salary">{salary}</span> : null}
        </div>

        <div className="card-row2">
          <span className="card-company" title={company}>
            {company}
          </span>
          {area ? <span className="card-area">{area}</span> : null}
          {activeText ? (
            <span className={`card-active-pill ${actCls}`} title={`HR活跃度：${activeText}`}>
              {activeText}
            </span>
          ) : null}
        </div>

        <div className="card-row3">
          {reason.note ? <span className="card-note-badge">{reason.note}</span> : null}
          <span className="card-snippet" title={reason.summarySnippet}>
            {reason.modular ? <span className="card-kind-icon">⚡</span> : null}
            {reason.dropCategory ? <span className="card-drop-tag">[{reason.dropCategory}] </span> : null}
            {reason.summarySnippet}
          </span>
        </div>
      </div>
    </div>
  )
}

export default memo(JobCard)
