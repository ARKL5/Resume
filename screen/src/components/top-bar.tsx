import { memo } from "react"
import { CITY_PAGES, STATIONS } from "../constants"
import {
  fileKey,
  fileLabel,
  type CityPage,
  type LaneId,
  type ScreenFile,
  type StationId,
} from "../types"

type Props = {
  files: ScreenFile[]
  selectedFile: string | null
  archiveOn: boolean
  offline: boolean
  onSelectFile: (fileKey: string) => void
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
  files,
  selectedFile,
  offline,
  onSelectFile,
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
        {/* 瑞士报头与文件索引 */}
        <div className="topbar-masthead">
          <span className="masthead-brand">SWISS // SCREEN</span>
          <div className="swiss-file-picker">
            <select
              className="swiss-select"
              value={selectedFile ?? ""}
              onChange={(e) => onSelectFile(e.target.value)}
              title="切换筛选结果文件"
            >
              {files.map((f) => {
                const k = fileKey(f)
                return (
                  <option key={k} value={k}>
                    {f.group === "archive" ? "[EXP] " : ""}
                    {fileLabel(f)}
                  </option>
                )
              })}
            </select>
          </div>
          {offline ? <span className="swiss-offline-flag">OFFLINE</span> : null}
        </div>

        {/* 城市分页 (01 杭州, 02 上海, 03 其它) */}
        <div className="topbar-city-group">
          <div className="swiss-segment-group">
            {CITY_PAGES.map((c, idx) => {
              const active = city === c
              const count = cityCounts[c] ?? 0
              return (
                <button
                  key={c}
                  type="button"
                  className={`swiss-segment-btn ${active ? "is-active" : ""}`}
                  onClick={() => onSelectCity(c)}
                >
                  <span className="seg-num">0{idx + 1}</span>
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

        {/* 圈岗与过滤检索 */}
        <div className="topbar-tool-group">
          <button
            type="button"
            className={`swiss-tool-btn ${onlyStar ? "is-active" : ""}`}
            onClick={onToggleOnlyStar}
            title="仅看圈岗岗位"
          >
            <span>{onlyStar ? "★" : "☆"} 圈岗</span>
            <span className="tool-count">[{starCount}]</span>
          </button>

          <div className="swiss-search-wrap">
            <span className="search-prefix">//</span>
            <input
              type="text"
              className="swiss-search-input"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="FILTER // 检索岗位/公司/停因..."
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
        </div>
      </div>

      {/* 二级切片细分条 */}
      {lanes.length > 0 ? (
        <div className="topbar-row-lanes">
          <span className="lanes-prefix">SUB-LANE //</span>
          <div className="lanes-button-group">
            <button
              type="button"
              className={`swiss-lane-chip ${lane === null ? "is-active" : ""}`}
              onClick={() => onSelectLane(null)}
            >
              ALL // 全部
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
