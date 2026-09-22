import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { lanesFor } from "./constants"
import { sortByReasonGroup } from "./groups"
import { loadStars, saveStars } from "./stars"
import TopBar from "./components/top-bar"
import MasterList from "./components/master-list"
import DetailInspector from "./components/detail-inspector"
import {
  bossHref,
  cityOf,
  defaultScreenKey,
  defaultStation,
  fileKey,
  isPlaced,
  jobKey,
  laneOf,
  stationOf,
  type CityPage,
  type LaneId,
  type ScreenFile,
  type ScreenItem,
  type StationId,
} from "./types"

function getUrlParams() {
  if (typeof window === "undefined") return { urlKey: null, station: null, query: "" }
  const params = new URLSearchParams(window.location.search)
  const paramFile = params.get("file")
  const paramGroup = params.get("group") || "seen"
  const paramStation = params.get("station") as StationId | null
  const paramQuery = params.get("q")
  return {
    urlKey: paramFile ? `${paramGroup}:${paramFile}` : null,
    station: paramStation && ["keep", "wait", "ai", "rule"].includes(paramStation) ? paramStation : null,
    query: paramQuery || "",
  }
}

export default function ScreenBoard() {
  const initialParams = useRef(getUrlParams())

  const [items, setItems] = useState<ScreenItem[]>([])
  const [files, setFiles] = useState<ScreenFile[]>([])
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [offline, setOffline] = useState(false)

  const [city, setCity] = useState<CityPage>("杭州")
  const [station, setStation] = useState<StationId>(() => initialParams.current.station || "keep")
  const [lane, setLane] = useState<LaneId | null>(null)
  const [query, setQuery] = useState(() => initialParams.current.query)
  const [onlyStar, setOnlyStar] = useState(false)
  const [stars, setStars] = useState<Set<string>>(() => new Set())
  const [selectedIndex, setSelectedIndex] = useState(0)

  const selectedRef = useRef<string | null>(null)
  const cityRef = useRef(city)
  cityRef.current = city
  const loadGen = useRef(0)
  const isInitialStationSet = useRef(Boolean(initialParams.current.station))
  const deferredQuery = useDeferredValue(query)

  // 1. 数据加载（不使用定时轮询打断对照与滚动，符合 ADR 0002）
  const load = useCallback(async (want?: string | null) => {
    const gen = ++loadGen.current
    try {
      const filesRes = await fetch("/api/screen-files")
      if (gen !== loadGen.current) return
      if (!filesRes.ok) throw new Error("files")
      const body: { files?: ScreenFile[] } = await filesRes.json()
      const listed = Array.isArray(body.files) ? body.files : []
      setFiles(listed)

      const names = new Set(listed.map((f) => fileKey(f)))
      const initialKey = initialParams.current.urlKey

      let file = want !== undefined ? want : selectedRef.current || (initialKey && names.has(initialKey) ? initialKey : null)
      if (!file || !names.has(file)) {
        file = defaultScreenKey(listed)
        selectedRef.current = file
        setSelectedFile(file)
        setSelectedIndex(0)
      } else if (!selectedRef.current) {
        selectedRef.current = file
        setSelectedFile(file)
      }

      if (!file) {
        setItems([])
        setOffline(false)
        return
      }

      const split = file.indexOf(":")
      const group = split >= 0 ? file.slice(0, split) : "seen"
      const name = split >= 0 ? file.slice(split + 1) : file
      const resultsRes = await fetch(
        `/api/screen-results?group=${encodeURIComponent(group)}&file=${encodeURIComponent(name)}`,
      )
      if (gen !== loadGen.current) return
      if (!resultsRes.ok) throw new Error("results")
      const data: { items?: ScreenItem[] } = await resultsRes.json()
      const validItems = (Array.isArray(data.items) ? data.items : []).filter(isPlaced)
      setItems(validItems)
      setOffline(false)

      // 首次加载或切换文件时，按决策优先规则选定默认停驻（保留 > 待读 > AI > 规则）
      if (!isInitialStationSet.current && validItems.length > 0) {
        isInitialStationSet.current = true
        setStation(defaultStation(validItems, cityRef.current))
      }
    } catch {
      if (gen !== loadGen.current) return
      setOffline(true)
    }
  }, [])

  useEffect(() => {
    setStars(loadStars())
    void load()
  }, [load])

  // 2. 圈岗操作
  const onToggleStar = useCallback((key: string) => {
    setStars((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      saveStars(next)
      return next
    })
  }, [])

  const onSelectFile = useCallback((k: string) => {
    selectedRef.current = k
    setSelectedFile(k)
    setLane(null)
    isInitialStationSet.current = false
    setSelectedIndex(0)
    void load(k)
  }, [load])

  const onSelectCity = useCallback((c: CityPage) => {
    setCity(c)
    setLane(null)
  }, [])

  const onSelectStation = useCallback((s: StationId) => {
    setStation(s)
    setLane(null)
  }, [])

  const onSelectLane = useCallback((l: LaneId | null) => {
    setLane(l)
  }, [])

  const onToggleOnlyStar = useCallback(() => {
    setOnlyStar((prev) => !prev)
  }, [])

  // 3. 统计计数
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
      if (cityOf(it) !== city) continue
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
    const m: Record<StationId, number> = { keep: 0, wait: 0, ai: 0, rule: 0 }
    for (const it of inCity) {
      const s = stationOf(it)
      if (s) m[s] += 1
    }
    return m
  }, [inCity])

  const lanes = lanesFor(station, city)

  const laneCounts = useMemo(() => {
    const m: Partial<Record<LaneId, number>> = {}
    for (const it of inCity) {
      if (stationOf(it) !== station) continue
      const l = laneOf(it)
      if (l) m[l] = (m[l] ?? 0) + 1
    }
    return m
  }, [inCity, station])

  const starCount = useMemo(() => {
    let n = 0
    for (const it of items) {
      if (cityOf(it) === city && stars.has(jobKey(it))) n += 1
    }
    return n
  }, [items, city, stars])

  // 4. 当前切片展示的最终岗位列表
  const displayItems = useMemo(() => {
    const ofStation: ScreenItem[] = []
    for (const it of inCity) {
      if (stationOf(it) !== station) continue
      if (lane && laneOf(it) !== lane) continue
      ofStation.push(it)
    }
    if (station === "rule") {
      return sortByReasonGroup(ofStation)
    }
    return ofStation
  }, [inCity, station, lane])

  // 切换维度时重置选中的卡片索引
  useEffect(() => {
    setSelectedIndex(0)
  }, [city, station, lane, deferredQuery, onlyStar])

  // 安全焦点索引
  const safeIndex = displayItems.length === 0 ? 0 : Math.min(selectedIndex, displayItems.length - 1)
  const currentItem = displayItems[safeIndex] ?? null

  // 5. 键盘快捷键监听
  const navRef = useRef({ items: displayItems, idx: safeIndex })
  navRef.current = { items: displayItems, idx: safeIndex }

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.tagName === "SELECT" ||
          t.tagName === "BUTTON" ||
          t.tagName === "A" ||
          t.isContentEditable)
      ) {
        return
      }

      const { items: list, idx } = navRef.current

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault()
        if (idx + 1 < list.length) {
          setSelectedIndex(idx + 1)
        }
        return
      }

      if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault()
        if (idx > 0) {
          setSelectedIndex(idx - 1)
        }
        return
      }

      // 快捷键 1:保留, 2:待读, 3:AI, 4:规则
      if (e.key === "1") {
        e.preventDefault()
        setStation("keep")
        setLane(null)
        return
      }
      if (e.key === "2") {
        e.preventDefault()
        setStation("wait")
        setLane(null)
        return
      }
      if (e.key === "3") {
        e.preventDefault()
        setStation("ai")
        setLane(null)
        return
      }
      if (e.key === "4") {
        e.preventDefault()
        setStation("rule")
        setLane(null)
        return
      }

      // s 或 Space 圈岗
      if (e.key === "s" || e.key === " ") {
        const it = list[idx]
        if (!it) return
        e.preventDefault()
        onToggleStar(jobKey(it))
        return
      }

      // Enter 或 o 直达 Boss 链接
      if (e.key === "Enter" || e.key === "o") {
        const it = list[idx]
        const href = it ? bossHref(it.href) : ""
        if (!href) return
        e.preventDefault()
        window.open(href, "_blank", "noopener,noreferrer")
      }
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [onToggleStar])

  const stationTitle = station === "keep" ? "保留" : station === "wait" ? "待读" : station === "ai" ? "AI" : "规则"
  const activeLaneObj = lanes.find((l) => l.id === lane)

  return (
    <div className="workbench-app">
      <TopBar
        files={files}
        selectedFile={selectedFile}
        offline={offline}
        onSelectFile={onSelectFile}
        city={city}
        onSelectCity={onSelectCity}
        cityCounts={cityCounts}
        station={station}
        onSelectStation={onSelectStation}
        stationCounts={stationCounts}
        lanes={lanes}
        lane={lane}
        onSelectLane={onSelectLane}
        laneCounts={laneCounts}
        query={query}
        onQueryChange={setQuery}
        onlyStar={onlyStar}
        onToggleOnlyStar={onToggleOnlyStar}
        starCount={starCount}
      />

      <div className="workbench-body">
        <MasterList
          items={displayItems}
          selectedIndex={safeIndex}
          stars={stars}
          onSelect={setSelectedIndex}
          onToggleStar={onToggleStar}
        />

        <DetailInspector
          item={currentItem}
          isStarred={currentItem ? stars.has(jobKey(currentItem)) : false}
          onToggleStar={onToggleStar}
          stationTitle={stationTitle}
          laneTitle={activeLaneObj?.title}
        />
      </div>
    </div>
  )
}
