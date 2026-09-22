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
    <header className="topbar">
      <div className="topbar-row-main">
        {/* 左区：文件选择与状态 */}
        <div className="topbar-file-section">
          <div className="file-select-wrapper">
            <span className="file-icon">📁</span>
            <select
              className="file-dropdown"
              value={selectedFile ?? ""}
              onChange={(e) => onSelectFile(e.target.value)}
              title="切换筛选结果文件"
            >
              {files.map((f) => {
                const k = fileKey(f)
                return (
                  <option key={k} value={k}>
                    {f.group === "archive" ? "[实验] " : ""}
                    {fileLabel(f)}
                  </option>
                )
              })}
            </select>
          </div>
          {offline ? <span className="offline-pill">离线 / 载入中</span> : null}
        </div>

        {/* 中区：城市分页 */}
        <div className="topbar-city-section">
          <div className="segmented-control city-control">
            {CITY_PAGES.map((c) => {
              const active = city === c
              const count = cityCounts[c] ?? 0
              return (
                <button
                  key={c}
                  type="button"
                  className={`segment-btn ${active ? "is-active" : ""}`}
                  onClick={() => onSelectCity(c)}
                >
                  <span className="city-name">{c}</span>
                  <span className="count-pill">{count}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* 右区：停驻切片 (1:保留, 2:待读, 3:AI, 4:规则) */}
        <div className="topbar-station-section">
          <div className="segmented-control station-control">
            {STATIONS.map((s) => {
              const active = station === s.id
              const count = stationCounts[s.id] ?? 0
              return (
                <button
                  key={s.id}
                  type="button"
                  className={`segment-btn ${s.tone} ${active ? "is-active" : ""}`}
                  onClick={() => onSelectStation(s.id)}
                  title={`快捷键: ${s.keyHint}`}
                >
                  <kbd className="key-kbd">{s.keyHint}</kbd>
                  <span className="station-name">{s.title}</span>
                  <span className="count-pill">{count}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* 圈岗与搜索过滤 */}
        <div className="topbar-filter-section">
          <button
            type="button"
            className={`star-filter-btn ${onlyStar ? "is-on" : ""}`}
            onClick={onToggleOnlyStar}
            title="仅看圈岗岗位"
          >
            <span className="star-icon">{onlyStar ? "★" : "☆"}</span>
            <span>圈岗</span>
            <span className="count-badge">{starCount}</span>
          </button>

          <div className="search-input-wrapper">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              className="search-input"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              placeholder="搜索岗位/公司/停因..."
            />
            {query ? (
              <button
                type="button"
                className="search-clear-btn"
                onClick={() => onQueryChange("")}
                title="清空"
              >
                ✕
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {/* 二级分类切片栏 */}
      {lanes.length > 0 ? (
        <div className="topbar-subrow-lanes">
          <span className="lanes-label">二级切片：</span>
          <div className="lanes-group">
            <button
              type="button"
              className={`lane-btn ${lane === null ? "is-active" : ""}`}
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
                  className={`lane-btn ${active ? "is-active" : ""}`}
                  onClick={() => onSelectLane(l.id)}
                >
                  <span>{l.title}</span>
                  <span className="lane-count">{count}</span>
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
