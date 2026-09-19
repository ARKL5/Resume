import { memo, useEffect, useRef } from "react"
import { bossHref, type ScreenItem } from "./types"

type Props = {
  item: ScreenItem
  itemKey: string
  starred: boolean
  active: boolean
  jdOpen: boolean
  onToggleStar: (key: string) => void
  onFocusRow: () => void
}

function JobRow({ item, itemKey, starred, active, jdOpen, onToggleStar, onFocusRow }: Props) {
  const rowRef = useRef<HTMLDivElement>(null)
  const hasJd = Boolean(item.hasJd || (item.jd && String(item.jd).trim()))
  const href = bossHref(item.href)
  const jobName = item.job || "（无岗位）"
  const area = item.area && String(item.area).trim()
  const activeText = item.active && String(item.active).trim()

  useEffect(() => {
    if (active && rowRef.current) {
      rowRef.current.scrollIntoView({ block: "nearest" })
    }
  }, [active])

  return (
    <div ref={rowRef} onClick={onFocusRow} className={active ? "row is-on" : "row"}>
      <button
        type="button"
        className={starred ? "mark is-on" : "mark"}
        onClick={(e) => {
          e.stopPropagation()
          onToggleStar(itemKey)
        }}
        aria-label={starred ? "取消圈岗" : "圈岗"}
      >
        {starred ? "●" : "○"}
      </button>
      <div className="body">
        <div className="line1">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="job"
              onClick={(e) => e.stopPropagation()}
            >
              {jobName}
            </a>
          ) : (
            <div className="job plain">{jobName}</div>
          )}
          <span className="co">{item.company || "（无公司）"}</span>
          {area || activeText ? (
            <span className="meta">
              {area ? <span>{area}</span> : null}
              {activeText ? <span>{activeText}</span> : null}
            </span>
          ) : null}
        </div>
        <div className="reason">{item.reason || item.status || "—"}</div>
        {jdOpen && hasJd ? <pre className="jd">{item.jd}</pre> : null}
      </div>
    </div>
  )
}

export default memo(JobRow)
