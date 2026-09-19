type Props = {
  total: number
  page: number
  pageSize: number
  onPage: (page: number) => void
}

function pageWindow(page: number, totalPages: number): number[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1)
  }
  const start = Math.max(1, Math.min(page - 2, totalPages - 4))
  const end = Math.min(totalPages, start + 4)
  const out: number[] = []
  for (let i = start; i <= end; i++) out.push(i)
  return out
}

export default function Pager({ total, page, pageSize, onPage }: Props) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= pageSize) return null
  const windowed = pageWindow(page, totalPages)

  return (
    <nav className="pager">
      <span>
        {total} 条 · {page}/{totalPages} 页
      </span>
      <div className="btns">
        <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          上一页
        </button>
        {windowed[0] > 1 ? (
          <>
            <button type="button" onClick={() => onPage(1)}>
              1
            </button>
            {windowed[0] > 2 ? <span>…</span> : null}
          </>
        ) : null}
        {windowed.map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => onPage(n)}
            className={n === page ? "is-on" : undefined}
          >
            {n}
          </button>
        ))}
        {windowed[windowed.length - 1] < totalPages ? (
          <>
            {windowed[windowed.length - 1] < totalPages - 1 ? <span>…</span> : null}
            <button type="button" onClick={() => onPage(totalPages)}>
              {totalPages}
            </button>
          </>
        ) : null}
        <button type="button" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
          下一页
        </button>
      </div>
    </nav>
  )
}
