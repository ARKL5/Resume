import type { CityPage, LaneId, StationId } from "./types"

export const CITY_PAGES: CityPage[] = ["杭州", "上海", "其它"]

export const STATIONS = [
  { id: "keep", title: "保留", tone: "s-keep", keyHint: "1" },
  { id: "wait", title: "待读", tone: "s-wait", keyHint: "2" },
  { id: "ai", title: "AI", tone: "s-ai", keyHint: "3" },
  { id: "rule", title: "规则", tone: "s-rule", keyHint: "4" },
] as const

export const AI_LANES: { id: LaneId; title: string }[] = [
  { id: "title_drop", title: "标题淘汰" },
  { id: "jd_drop", title: "JD淘汰" },
  { id: "title_fail", title: "标题失败" },
  { id: "jd_fail", title: "JD失败" },
]

export const WAIT_LANES: { id: LaneId; title: string }[] = [
  { id: "click_cap", title: "待点" },
  { id: "park", title: "含糊" },
]

export function lanesFor(station: StationId): { id: LaneId; title: string }[] {
  if (station === "ai") return AI_LANES
  if (station === "wait") return WAIT_LANES
  return []
}
