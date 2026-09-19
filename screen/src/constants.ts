import type { CityPage } from "./types"

export const CITY_PAGES: CityPage[] = ["杭州", "上海", "其它"]

export const STAGES = [
  { id: 1, title: "列表规则" },
  { id: 2, title: "列表 CPA" },
  { id: 3, title: "详情" },
  { id: 4, title: "CPA 保留" },
] as const
