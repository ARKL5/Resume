import { memo } from "react"
import { CITY_PAGES, STATIONS } from "../constants"
import { batchLabel, type CityPage, type LaneId, type StationId } from "../types"

type Props = {
  totalCount: number
  offline: boolean
  onRefresh: () => void
  batches: string[]
  batch: string
  onSelectBatch: (batch: string) => void
  city: CityPage
  onSelectCity: (city: CityPage) => void
  cityCounts: Record<CityPage, number>
  station: StationId
  onSelectStation: (station: StationId) => void
  stationCounts: Record<StationId, number>
  lanes: { id: LaneId; title: string }[]
  lane: LaneId | null
  onSelectLane: (lane: LaneId | null) => void
  laneCounts: Partial<Record<LaneId, number>>
  query: string
  onQueryChange: (query: string) => void
  onlyStar: boolean
  onToggleOnlyStar: () => void
  starCount: number
}

function TopBar({
  totalCount,
  offline,
  onRefresh,
  batches,
  batch,
  onSelectBatch,
  city,
  onSelectCity,
  cityCounts,
  station,
  onSelectStation,
  stationCounts,
  lanes,
  lane,
  onSelectLane,
  laneCounts,
  query,
  onQueryChange,
  onlyStar,
  onToggleOnlyStar,
  starCount,
}: Props) {
  return (
    <header className="swiss-topbar">
      <div className="topbar-row-primary">
        {/* 报头与单库状态 */}
        <div className="topbar-masthead">
          <button
            type="button"
            className="swiss-tool-btn"
            onClick={onRefresh}
            title="从 SQLite 刷新最新流式结果 (快捷键 r)"
          >
            <span>{totalCount} 岗</span>
            <span className="tool-count">[刷新 r]</span>
          </button>
          {offline ? <span className="swiss-offline-flag">OFFLINE</span> : null}
        </div>

        {/* 城市分页 (01 杭州, 02 上海, 03 其它) */}
        <div className="topbar-city-group">
          <div className="swiss-segment-group">
            {CITY_PAGES.map((c) => {
              const active = city === c
              const count = cityCounts[c] ?? 0
              return (
                <button
                  key={c}
                  type="button"
                  className={`swiss-segment-btn ${active ? "is-active" : ""}`}
                  onClick={() => onSelectCity(c)}
                >
                  <span className="seg-label">{c}</span>
                  <span className="seg-count">[{count}]</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* 停驻切片 (1:保留, 2:待读, 3:AI, 4:规则) */}
        <div className="topbar-station-group">
          <div className="swiss-segment-group">
            {STATIONS.map((s) => {
              const active = station === s.id
              const count = stationCounts[s.id] ?? 0
              return (
                <button
                  key={s.id}
                  type="button"
                  className={`swiss-segment-btn ${s.tone} ${active ? "is-active" : ""}`}
                  onClick={() => onSelectStation(s.id)}
                  title={`快捷键: ${s.keyHint}`}
                >
                  <span className="seg-num">[{s.keyHint}]</span>
                  <span className="seg-label">{s.title}</span>
                  <span className="seg-count">[{count}]</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* 批次筛选：同一轮筛选共用一个时间 */}
        {batches.length > 0 ? (
          <div className="topbar-batch-group">
            <label className="swiss-batch-picker">
              <span className="batch-label">批次</span>
              <select
                className="swiss-batch-select"
                value={batch}
                onChange={(e) => onSelectBatch(e.target.value)}
                title="按筛选批次过滤岗位"
              >
                <option value="">全部</option>
                {batches.map((key) => (
                  <option key={key} value={key}>
                    {batchLabel(key)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : null}

        <button
          type="button"
          className={`swiss-tool-btn topbar-star ${onlyStar ? "is-active" : ""}`}
          onClick={onToggleOnlyStar}
          title="仅看圈岗岗位"
        >
          <span>{onlyStar ? "★" : "☆"} 圈岗</span>
          <span className="tool-count">[{starCount}]</span>
        </button>

        <div className="swiss-search-wrap">
          <input
            type="text"
            className="swiss-search-input"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="检索岗位、公司或停因"
          />
          {query ? (
            <button
              type="button"
              className="swiss-clear-btn"
              onClick={() => onQueryChange("")}
            >
              [X]
            </button>
          ) : null}
        </div>
        <div className="topbar-line-break" aria-hidden="true" />
      </div>

      {/* 二级切片细分条 */}
      {lanes.length > 0 ? (
        <div className="topbar-row-lanes">
          <div className="lanes-button-group">
            <button
              type="button"
              className={`swiss-lane-chip ${lane === null ? "is-active" : ""}`}
              onClick={() => onSelectLane(null)}
            >
              全部
            </button>
            {lanes.map((l) => {
              const active = lane === l.id
              const count = laneCounts[l.id] ?? 0
              return (
                <button
                  key={l.id}
                  type="button"
                  className={`swiss-lane-chip ${active ? "is-active" : ""}`}
                  onClick={() => onSelectLane(l.id)}
                >
                  <span>{l.title}</span>
                  <span className="chip-count">[{count}]</span>
                </button>
              )
            })}
          </div>
        </div>
      ) : null}
    </header>
  )
}

export default memo(TopBar)
