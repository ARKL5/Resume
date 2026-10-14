import { memo, useEffect, useRef } from "react"
import { itemReason } from "../reason"
import { activeClass, jobKey, type ScreenItem } from "../types"

type Props = {
  item: ScreenItem
  index: number
  isSelected: boolean
  isStarred: boolean
  onSelect: (index: number) => void
  onToggleStar: (key: string) => void
}

function JobCard({ item, index, isSelected, isStarred, onSelect, onToggleStar }: Props) {
  const cardRef = useRef<HTMLDivElement>(null)
  const key = jobKey(item)
  const jobName = item.job || "（未命名岗位）"
  const company = item.company || "（未标明公司）"
  const area = item.area.trim()
  const salary = item.salary?.trim()
  const activeText = item.active.trim()
  const reason = itemReason(item)
  const actCls = activeClass(activeText)

  useEffect(() => {
    if (isSelected && cardRef.current) {
      cardRef.current.scrollIntoView({ block: "nearest" })
    }
  }, [isSelected])

  return (
    <div
      ref={cardRef}
      onClick={() => onSelect(index)}
      className={`swiss-card ${isSelected ? "is-selected" : ""} ${isStarred ? "is-starred" : ""}`}
    >
      <div className="card-top-row">
        <button
          type="button"
          className={`swiss-star ${isStarred ? "is-on" : ""}`}
          onClick={(e) => {
            e.stopPropagation()
            onToggleStar(key)
          }}
          title={isStarred ? "取消圈岗 (s)" : "圈岗 (s)"}
          aria-label={isStarred ? "取消圈岗" : "圈岗"}
        >
          {isStarred ? "★" : "☆"}
        </button>

        <span className="card-title" title={jobName}>
          {jobName}
        </span>

        {salary ? <span className="card-salary">{salary}</span> : null}
      </div>

      <div className="card-meta-row">
        <span className="card-company" title={company}>
          {company}
        </span>
        {area ? <span className="card-area">/ {area}</span> : null}
        {activeText ? (
          <span className={`card-active-tag ${actCls}`} title={`HR活跃度：${activeText}`}>
            {activeText}
          </span>
        ) : null}
      </div>

      <div className="card-snippet-row">
        <span className="card-snippet-text" title={reason.summarySnippet}>
          {reason.modular ? <span className="swiss-symbol">§ </span> : null}
          {reason.dropCategory ? <span className="swiss-drop-tag">[{reason.dropCategory}] </span> : null}
          {reason.summarySnippet}
        </span>
      </div>
    </div>
  )
}

export default memo(JobCard)
