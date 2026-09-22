import { memo } from "react"
import JobCard from "./job-card"
import { jobKey, type ScreenItem } from "../types"

type Props = {
  items: ScreenItem[]
  selectedIndex: number
  stars: Set<string>
  onSelect: (index: number) => void
  onToggleStar: (key: string) => void
}

function MasterList({ items, selectedIndex, stars, onSelect, onToggleStar }: Props) {
  if (items.length === 0) {
    return (
      <aside className="master-list is-empty">
        <div className="empty-notice">
          <div className="empty-icon">📭</div>
          <div className="empty-title">当前切片下无岗位</div>
          <div className="empty-desc">尝试切换停驻、分类或清除搜索关键词</div>
        </div>
      </aside>
    )
  }

  return (
    <aside className="master-list">
      <div className="list-meta-bar">
        <span className="count-label">
          当前列表 <strong>{items.length}</strong> 岗
        </span>
        <span className="kb-hint">快捷键 j / k 切换</span>
      </div>

      <div className="list-scroll-area">
        {items.map((it, idx) => {
          const key = jobKey(it)
          return (
            <JobCard
              key={key}
              item={it}
              isSelected={idx === selectedIndex}
              isStarred={stars.has(key)}
              onSelect={() => onSelect(idx)}
              onToggleStar={onToggleStar}
            />
          )
        })}
      </div>
    </aside>
  )
}

export default memo(MasterList)
