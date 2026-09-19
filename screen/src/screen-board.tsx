import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { apiUrl } from "./api"
import { CITY_PAGES, STAGES } from "./constants"
import { pageSizeForViewport } from "./page-size"
import { loadStars, saveStars } from "./stars"
import { sortByReasonGroup } from "./groups"
import StageTable from "./stage-table"
import {
  bossHref,
  cityOf,
  columnOf,
  jobKey,
  type BossStatus,
  type CityPage,
  type ScreenItem,
} from "./types"

type NavSnap = {
  slice: ScreenItem[]
  page: number
  totalPages: number
  hi: number
}

export default function ScreenBoard() {
  const [items, setItems] = useState<ScreenItem[]>([])
  const [status, setStatus] = useState<BossStatus | null>(null)
  const [city, setCity] = useState<CityPage>("杭州")
  const [stage, setStage] = useState(1)
  const [query, setQuery] = useState("")
  const [onlyStar, setOnlyStar] = useState(false)
  const [stars, setStars] = useState<Set<string>>(() => new Set())
  const [offline, setOffline] = useState(false)
  const [page, setPage] = useState(1)
  const [hi, setHi] = useState(0)
  const [jdOpenKey, setJdOpenKey] = useState<string | null>(null)
  const [pageSize, setPageSize] = useState(24)
  const deferredQuery = useDeferredValue(query)
  const stale = query !== deferredQuery
  const navRef = useRef<NavSnap>({ slice: [], page: 1, totalPages: 1, hi: 0 })

  const load = useCallback(async () => {
    try {
      const [resultsRes, statusRes] = await Promise.all([
        fetch(apiUrl("/api/boss/screen-results")),
        fetch(apiUrl("/api/boss/status")),
      ])
      if (!resultsRes.ok) throw new Error("results")
      const data: { items?: ScreenItem[] } = await resultsRes.json()
      setItems(Array.isArray(data.items) ? data.items : [])
      if (statusRes.ok) {
        setStatus(await statusRes.json())
      }
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [])

  useEffect(() => {
    setStars(loadStars())
    void load()
    const id = window.setInterval(() => void load(), 4000)
    return () => window.clearInterval(id)
  }, [load])

  const onToggleStar = useCallback((key: string) => {
    setStars((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      saveStars(next)
      return next
    })
  }, [])

  const ackHuman = useCallback(async () => {
    try {
      await fetch(apiUrl("/api/boss/ack-human"), { method: "POST" })
    } catch {
      // ignore
    }
    void load()
  }, [load])

  const cityCounts = useMemo(() => {
    const m: Record<CityPage, number> = { 杭州: 0, 上海: 0, 其它: 0 }
    for (const it of items) m[cityOf(it)] += 1
    return m
  }, [items])

  const inCity = useMemo(() => {
    const q = deferredQuery.trim().toLowerCase()
    const out: ScreenItem[] = []
    for (const it of items) {
      if (cityOf(it) !== city) continue
      const k = jobKey(it)
      if (onlyStar && !stars.has(k)) continue
      if (q) {
        const blob = [it.company, it.job, it.reason, it.keyword, it.status, it.area, it.active]
          .concat(it.keywords || [])
          .join(" ")
          .toLowerCase()
        if (!blob.includes(q)) continue
      }
      out.push(it)
    }
    return out
  }, [items, city, onlyStar, stars, deferredQuery])

  const stageCounts = useMemo(() => {
    const m = [0, 0, 0, 0]
    for (const it of inCity) m[columnOf(it) - 1] += 1
    return m
  }, [inCity])

  const ranked = useMemo(() => {
    const ofStage: ScreenItem[] = []
    for (const it of inCity) {
      if (columnOf(it) === stage) ofStage.push(it)
    }
    return sortByReasonGroup(ofStage)
  }, [inCity, stage])

  useEffect(() => {
    const measure = () => setPageSize(pageSizeForViewport(window.innerWidth, window.innerHeight))
    measure()
    window.addEventListener("resize", measure)
    return () => window.removeEventListener("resize", measure)
  }, [])

  const totalPages = Math.max(1, Math.ceil(ranked.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const start = (safePage - 1) * pageSize
  const slice = useMemo(() => ranked.slice(start, start + pageSize), [ranked, start, pageSize])
  const safeHi = slice.length === 0 ? 0 : Math.min(hi, slice.length - 1)

  navRef.current = { slice, page: safePage, totalPages, hi: safeHi }

  useEffect(() => {
    setPage(1)
    setHi(0)
    setJdOpenKey(null)
  }, [city, stage, deferredQuery, onlyStar])

  useEffect(() => {
    setPage((p) => Math.min(p, totalPages))
  }, [totalPages])

  const starN = useMemo(() => {
    let n = 0
    for (const it of items) {
      if (cityOf(it) === city && stars.has(jobKey(it))) n += 1
    }
    return n
  }, [items, city, stars])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return
      const snap = navRef.current
      const key = e.key
      if (key === "j" || key === "ArrowDown") {
        e.preventDefault()
        if (snap.hi + 1 < snap.slice.length) setHi(snap.hi + 1)
        else if (snap.page < snap.totalPages) {
          setPage(snap.page + 1)
          setHi(0)
        }
        return
      }
      if (key === "k" || key === "ArrowUp") {
        e.preventDefault()
        if (snap.hi > 0) setHi(snap.hi - 1)
        else if (snap.page > 1) {
          setPage(snap.page - 1)
          setHi(Number.MAX_SAFE_INTEGER)
        }
        return
      }
      if (key === "n" || key === "ArrowRight") {
        e.preventDefault()
        if (snap.page < snap.totalPages) {
          setPage(snap.page + 1)
          setHi(0)
        }
        return
      }
      if (key === "p" || key === "ArrowLeft") {
        e.preventDefault()
        if (snap.page > 1) {
          setPage(snap.page - 1)
          setHi(0)
        }
        return
      }
      if (key === "1" || key === "2" || key === "3" || key === "4") {
        setStage(Number(key))
        return
      }
      if (key === "s" || key === " ") {
        const it = snap.slice[snap.hi]
        if (!it) return
        e.preventDefault()
        onToggleStar(jobKey(it))
        return
      }
      if (key === "d") {
        const it = snap.slice[snap.hi]
        if (!it) return
        const hasJd = Boolean(it.hasJd || (it.jd && String(it.jd).trim()))
        if (!hasJd) return
        e.preventDefault()
        const k = jobKey(it)
        setJdOpenKey((cur) => (cur === k ? null : k))
        return
      }
      if (key === "Enter") {
        const it = snap.slice[snap.hi]
        const href = it ? bossHref(it.href) : ""
        if (!href) return
        e.preventDefault()
        window.open(href, "_blank", "noreferrer")
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onToggleStar])

  const running = Boolean(status?.isRunning || status?.running)
  const needHuman = Boolean(status?.needHuman)

  return (
    <div className="page">
      <div className="toolbar">
        <div className="tabs">
          {CITY_PAGES.map((p) => (
            <button
              key={p}
              type="button"
              className={city === p ? "tab is-on" : "tab"}
              onClick={() => setCity(p)}
            >
              {p}
              <span className="n">{cityCounts[p]}</span>
            </button>
          ))}
        </div>
        <div className="tabs">
          {STAGES.map((def, idx) => (
            <button
              key={def.id}
              type="button"
              className={stage === def.id ? "tab is-on" : "tab"}
              onClick={() => setStage(def.id)}
            >
              {def.title}
              <span className="n">{stageCounts[idx]}</span>
            </button>
          ))}
        </div>
        <span className="status">
          <b>{offline ? "连不上 9527" : running ? "筛选进行中" : "空闲"}</b>
          <span className="n"> {items.length}</span>
        </span>
      </div>

      {needHuman ? (
        <div className="human">
          <div>
            <p>需要你处理人机验证或登录</p>
            <p className="sub">{status?.needHumanReason || "请到 get_jobs 拉起的 Chrome 处理。"}</p>
          </div>
          <button type="button" onClick={() => void ackHuman()}>
            我处理好了，继续
          </button>
        </div>
      ) : null}

      <div className="search-row">
        <div className="search">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜公司 / 岗位 / 停因 / 搜索词"
          />
        </div>
        <button
          type="button"
          className={onlyStar ? "text-btn is-on" : "text-btn"}
          onClick={() => setOnlyStar((v) => !v)}
        >
          已圈 {starN}
        </button>
        <button type="button" className="text-btn" onClick={() => void load()}>
          刷新
        </button>
      </div>

      <div className={stale ? "stale" : undefined}>
        <StageTable
          items={ranked}
          page={safePage}
          pageSize={pageSize}
          onPage={(p) => {
            setPage(p)
            setHi(0)
          }}
          hi={safeHi}
          onHi={setHi}
          starred={stars}
          jdOpenKey={jdOpenKey}
          onToggleStar={onToggleStar}
        />
      </div>
    </div>
  )
}
