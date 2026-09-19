import { memo, useMemo } from "react"
import JobRow from "./job-row"
import Pager from "./pager"
import { reasonGroup } from "./groups"
import { jobKey, type ScreenItem } from "./types"

type Props = {
  items: ScreenItem[]
  page: number
  pageSize: number
  onPage: (page: number) => void
  hi: number
  onHi: (index: number) => void
  starred: Set<string>
  jdOpenKey: string | null
  onToggleStar: (key: string) => void
}

type Group = { label: string; entries: { it: ScreenItem; i: number }[] }

function StageTable({ items, page, pageSize, onPage, hi, onHi, starred, jdOpenKey, onToggleStar }: Props) {
  const totalPages = Math.max(1, Math.ceil(items.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const start = (safePage - 1) * pageSize
  const slice = useMemo(() => items.slice(start, start + pageSize), [items, start, pageSize])
  const groups = useMemo(() => {
    const out: Group[] = []
    slice.forEach((it, i) => {
      const label = reasonGroup(it)
      const last = out[out.length - 1]
      if (!last || last.label !== label) out.push({ label, entries: [{ it, i }] })
      else last.entries.push({ it, i })
    })
    return out
  }, [slice])

  if (items.length === 0) {
    return <p className="empty">没有岗</p>
  }

  return (
    <div>
      {groups.map((g) => (
        <div key={`${g.label}-${g.entries[0].i}`}>
          <div className="group-h">
            {g.label}
            <span className="n">{g.entries.length}</span>
          </div>
          <div className="jobs">
            {g.entries.map(({ it, i }) => {
              const k = jobKey(it)
              const open = jdOpenKey === k
              return (
                <div key={k} className={open ? "cell is-open" : "cell"}>
                  <JobRow
                    item={it}
                    itemKey={k}
                    starred={starred.has(k)}
                    active={i === hi}
                    jdOpen={open}
                    onToggleStar={onToggleStar}
                    onFocusRow={() => onHi(i)}
                  />
                </div>
              )
            })}
          </div>
        </div>
      ))}
      <Pager total={items.length} page={safePage} pageSize={pageSize} onPage={onPage} />
    </div>
  )
}

export default memo(StageTable)
