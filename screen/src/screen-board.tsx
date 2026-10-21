import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { lanesFor, STATIONS } from "./constants"
import { sortByReasonGroup } from "./groups"
import { loadStars, saveStars } from "./stars"
import TopBar from "./components/top-bar"
import MasterList from "./components/master-list"
import DetailInspector from "./components/detail-inspector"
import {
  batchKey,
  batchKeys,
  bossHref,
  cityOf,
  defaultStation,
  isPlaced,
  jobKey,
  laneOf,
  stationOf,
  type CityPage,
  type LaneId,
  type ScreenItem,
  type StationId,
} from "./types"

function getUrlParams() {
  const params = new URLSearchParams(window.location.search)
  const paramStation = STATIONS.find((s) => s.id === params.get("station"))
  const paramQuery = params.get("q")
  return {
    station: paramStation?.id ?? null,
    query: paramQuery || "",
  }
}

export default function ScreenBoard() {
  const [initialParams] = useState(getUrlParams)

  const [items, setItems] = useState<ScreenItem[]>([])
  const [offline, setOffline] = useState(false)

  const [city, setCity] = useState<CityPage>("杭州")
  const [station, setStation] = useState<StationId>(() => initialParams.station || "keep")
  const [lane, setLane] = useState<LaneId | null>(null)
  const [query, setQuery] = useState(initialParams.query)
  const [batch, setBatch] = useState("")
  const [onlyStar, setOnlyStar] = useState(false)
  const [stars, setStars] = useState<Set<string>>(() => new Set())
  const [selectedIndex, setSelectedIndex] = useState(0)

  const cityRef = useRef(city)
  cityRef.current = city
  const loadGen = useRef(0)
  const batchPicked = useRef(false)
  const deferredQuery = useDeferredValue(query)

  const loadResults = useCallback(async (preferredStation?: StationId | null) => {
    const gen = ++loadGen.current
    try {
      const response = await fetch("/api/screen-results")
      if (!response.ok) throw new Error("results")
      const data: { items: ScreenItem[] } = await response.json()
      if (gen !== loadGen.current) return
      const validItems = data.items.filter(isPlaced)
      setItems(validItems)
      setOffline(false)
      if (preferredStation !== undefined && validItems.length > 0) {
        const latest = batchKeys(validItems)[0] ?? ""
        const considered = latest
          ? validItems.filter((item) => batchKey(item.batchAt) === latest)
          : validItems
        setStation(preferredStation ?? defaultStation(considered, cityRef.current))
      }
    } catch {
      if (gen !== loadGen.current) return
      setOffline(true)
    }
  }, [])

  useEffect(() => {
    setStars(loadStars())
    void loadResults(initialParams.station)
  }, [initialParams, loadResults])

  const onRefresh = useCallback(() => {
    void loadResults()
  }, [loadResults])

  const onToggleStar = useCallback((key: string) => {
    setStars((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      saveStars(next)
      return next
    })
  }, [])

  const onSelectCity = useCallback((c: CityPage) => {
    setCity(c)
    setLane(null)
  }, [])

  const onSelectStation = useCallback((s: StationId) => {
    setStation(s)
    setLane(null)
  }, [])

  const onToggleOnlyStar = useCallback(() => {
    setOnlyStar((prev) => !prev)
  }, [])

  const onSelectBatch = useCallback((next: string) => {
    batchPicked.current = true
    setBatch(next)
  }, [])

  const batchList = useMemo(() => batchKeys(items), [items])

  // 未手动选批次时始终跟到最新一轮，刷新出新一轮也不用再点一次。
  useEffect(() => {
    if (batchPicked.current) return
    const latest = batchList[0]
    if (latest && latest !== batch) setBatch(latest)
  }, [batchList, batch])

  const inBatch = useMemo(() => {
    if (!batch) return items
    return items.filter((item) => batchKey(item.batchAt) === batch)
  }, [items, batch])

  const cityCounts = useMemo(() => {
    const m: Record<CityPage, number> = { 杭州: 0, 上海: 0, 其它: 0 }
    for (const it of inBatch) {
      const c = cityOf(it)
      if (c) m[c] += 1
    }
    return m
  }, [inBatch])

  const inCity = useMemo(() => {
    const q = deferredQuery.trim().toLowerCase()
    const out: ScreenItem[] = []
    for (const it of inBatch) {
      if (cityOf(it) !== city) continue
      const k = jobKey(it)
      if (onlyStar && !stars.has(k)) continue
      if (q) {
        const blob = [it.company, it.job, it.reason, it.keyword, it.area, it.active, it.tags || ""]
          .concat(it.keywords)
          .join(" ")
          .toLowerCase()
        if (!blob.includes(q)) continue
      }
      out.push(it)
    }
    return out
  }, [inBatch, city, onlyStar, stars, deferredQuery])

  const stationCounts = useMemo(() => {
    const m: Record<StationId, number> = { keep: 0, wait: 0, ai: 0, rule: 0 }
    for (const it of inCity) {
      const s = stationOf(it)
      if (s) m[s] += 1
    }
    return m
  }, [inCity])

  const lanes = lanesFor(station)

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
    for (const it of inBatch) {
      if (cityOf(it) === city && stars.has(jobKey(it))) n += 1
    }
    return n
  }, [inBatch, city, stars])

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

  useEffect(() => {
    setSelectedIndex(0)
  }, [city, station, lane, deferredQuery, onlyStar, batch])

  const safeIndex = displayItems.length === 0 ? 0 : Math.min(selectedIndex, displayItems.length - 1)
  const currentItem = displayItems[safeIndex] ?? null

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

      if (e.key === "r") {
        e.preventDefault()
        onRefresh()
        return
      }

      const targetStation = STATIONS.find((s) => s.keyHint === e.key)
      if (targetStation) {
        e.preventDefault()
        onSelectStation(targetStation.id)
        return
      }

      if (e.key === "s" || e.key === " ") {
        const it = list[idx]
        if (!it) return
        e.preventDefault()
        onToggleStar(jobKey(it))
        return
      }

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
  }, [onToggleStar, onSelectStation, onRefresh])

  const stationTitle = STATIONS.find((s) => s.id === station)!.title
  const activeLaneObj = lanes.find((l) => l.id === lane)

  return (
    <div className="workbench-app">
      <TopBar
        totalCount={inBatch.length}
        offline={offline}
        onRefresh={onRefresh}
        batches={batchList}
        batch={batch}
        onSelectBatch={onSelectBatch}
        city={city}
        onSelectCity={onSelectCity}
        cityCounts={cityCounts}
        station={station}
        onSelectStation={onSelectStation}
        stationCounts={stationCounts}
        lanes={lanes}
        lane={lane}
        onSelectLane={setLane}
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
