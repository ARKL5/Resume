import type { CityPage, StationId } from "./types"

export const CITY_PAGES: CityPage[] = ["杭州", "上海", "其它"]

export const STATIONS: { id: StationId; title: string; tone: string }[] = [
  { id: "rule", title: "规则", tone: "s1" },
  { id: "ai", title: "AI", tone: "s2" },
  { id: "wait", title: "待读", tone: "s3" },
  { id: "keep", title: "保留", tone: "s4" },
]
