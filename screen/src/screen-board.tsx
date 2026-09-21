import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { apiUrl } from "./api"
import { CITY_PAGES, STATIONS } from "./constants"
import { pageSizeForViewport } from "./page-size"
import { loadStars, saveStars } from "./stars"
import { sortByReasonGroup } from "./groups"
import StationTable from "./station-table"
import {
  bossHref,
  cityOf,
  fileLabel,
  isPlaced,
  jobKey,
  stationOf,
  type BossStatus,
  type CityPage,
  type ScreenFile,
  type ScreenItem,
  type StationId,
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
  const [files, setFiles] = useState<ScreenFile[]>([])
  const [pinnedFile, setPinnedFile] = useState<string | null>(null)
  const [loadedFile, setLoadedFile] = useState("")
  const pinnedRef = useRef<string | null>(null)
  const loadGen = useRef(0)
  const [city, setCity] = useState<CityPage>("杭州")
  const [station, setStation] = useState<StationId>("rule")
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

  const load = useCallback(async (file = pinnedRef.current) => {
    const gen = ++loadGen.current
    try {
      const resultsPath = file
        ? `/api/boss/screen-results?file=${encodeURIComponent(file)}`
        : "/api/boss/screen-results"
      const [resultsRes, statusRes, filesRes] = await Promise.all([
        fetch(apiUrl(resultsPath)),
        fetch(apiUrl("/api/boss/status")),
        fetch(apiUrl("/api/boss/screen-files")),
      ])
      if (gen !== loadGen.current) return
      if (!resultsRes.ok) throw new Error("results")
      const data: { items?: ScreenItem[]; file?: string } = await resultsRes.json()
      setItems((Array.isArray(data.items) ? data.items : []).filter(isPlaced))
      setLoadedFile(typeof data.file === "string" ? data.file : file ?? "")
      if (statusRes.ok) {
        setStatus(await statusRes.json())
      }
      if (filesRes.ok) {
        const listed: { files?: ScreenFile[] } = await filesRes.json()
        setFiles(Array.isArray(listed.files) ? listed.files : [])
      }
      setOffline(false)
    } catch {
      if (gen !== loadGen.current) return
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
    for (const it of items) {
      const c = cityOf(it)
      if (c) m[c] += 1
    }
    return m
  }, [items])

  const inCity = useMemo(() => {
    const q = deferredQuery.trim().toLowerCase()
    const out: ScreenItem[] = []
    for (const it of items) {
      if (cityOf(it) !== city || !stationOf(it)) continue
      const k = jobKey(it)
      if (onlyStar && !stars.has(k)) continue
      if (q) {
        const blob = [it.company, it.job, it.reason, it.keyword, it.area, it.active]
          .concat(it.keywords || [])
          .join(" ")
          .toLowerCase()
        if (!blob.includes(q)) continue
      }
      out.push(it)
    }
    return out
  }, [items, city, onlyStar, stars, deferredQuery])

  const stationCounts = useMemo(() => {
    const m: Record<StationId, number> = { rule: 0, ai: 0, wait: 0, keep: 0 }
    for (const it of inCity) {
      const s = stationOf(it)
      if (s) m[s] += 1
    }
    return m
  }, [inCity])

  const ranked = useMemo(() => {
    const ofStation: ScreenItem[] = []
    for (const it of inCity) {
      if (stationOf(it) === station) ofStation.push(it)
    }
    return sortByReasonGroup(ofStation)
  }, [inCity, station])

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
  }, [city, station, deferredQuery, onlyStar])

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
        const next = STATIONS[Number(key) - 1]
        if (next) setStation(next.id)
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

  const running = Boolean(status?.isRunning)
  const needHuman = Boolean(status?.needHuman)

  return (
    <div className="page">
      <div className="toolbar">
        <div className="tabs">
          {CITY_PAGES.map((p) => (
            <button
              key={p}
              type="button"
              className={city === p ? "tab city is-on" : "tab city"}
              onClick={() => setCity(p)}
            >
              {p}
              <span className="n">{cityCounts[p]}</span>
            </button>
          ))}
        </div>
        <div className="tabs">
          {STATIONS.map((def) => (
            <button
              key={def.id}
              type="button"
              className={station === def.id ? `tab ${def.tone} is-on` : `tab ${def.tone}`}
              onClick={() => setStation(def.id)}
            >
              {def.title}
              <span className="n">{stationCounts[def.id]}</span>
            </button>
          ))}
        </div>
        <span className={offline ? "status is-off" : running ? "status is-run" : "status"}>
          <b>{offline ? "连不上 9527" : running ? "筛选进行中" : "空闲"}</b>
          <span className="n"> {items.length}</span>
          {loadedFile ? <span className="file-name"> {loadedFile}</span> : null}
        </span>
      </div>

      {needHuman ? (
        <div className="human">
          <div>
            <p>需要你处理人机验证或登录</p>
            <p className="sub">{status?.needHumanReason || "请到 Boss 拉起的 Chrome 处理。"}</p>
          </div>
          <button type="button" onClick={() => void ackHuman()}>
            我处理好了，继续
          </button>
        </div>
      ) : null}

      <div className="search-row">
        <div className="file-pick">
          <select
            value={pinnedFile ?? ""}
            onChange={(e) => {
              const v = e.target.value === "" ? null : e.target.value
              pinnedRef.current = v
              setPinnedFile(v)
              setPage(1)
              setHi(0)
              void load(v)
            }}
          >
            <option value="">跟着筛选</option>
            {files.map((f) => (
              <option key={f.name} value={f.name}>
                {fileLabel(f)}
              </option>
            ))}
          </select>
        </div>
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
        <StationTable
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
