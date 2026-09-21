import type { CityPage, LaneId, StationId } from "./types"

export const CITY_PAGES: CityPage[] = ["杭州", "上海", "其它"]

export const STATIONS: { id: StationId; title: string; tone: string }[] = [
  { id: "rule", title: "规则", tone: "s1" },
  { id: "ai", title: "AI", tone: "s2" },
  { id: "wait", title: "待读", tone: "s3" },
  { id: "keep", title: "保留", tone: "s4" },
]

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

export function lanesFor(station: StationId, city: CityPage): { id: LaneId; title: string }[] {
  if (station === "ai") return AI_LANES
  if (station === "wait" && city !== "其它") return WAIT_LANES
  return []
}
