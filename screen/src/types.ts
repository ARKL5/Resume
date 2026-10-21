import type { STATIONS } from "./constants"

export type Stage =
  | "rule_drop"
  | "ai_title_drop"
  | "ai_title_pending"
  | "jd_park"
  | "jd_queued"
  | "ai_jd_pending"
  | "ai_jd_drop"
  | "ai_keep"

export type ScreenItem = {
  encryptId: string
  company: string
  job: string
  keyword: string
  keywords: string[]
  area: string
  active: string
  salary?: string
  href: string
  tags?: string
  jd?: string
  recruiter?: string
  recruiterTitle?: string
  degree?: string
  experience?: string
  industry?: string
  scale?: string
  financing?: string
  stage: Stage
  reason: string
  cityPage: CityPage
  batchAt: string
}

export type CityPage = "杭州" | "上海" | "其它"

export type StationId = (typeof STATIONS)[number]["id"]

export function defaultStation(items: ScreenItem[], city: CityPage): StationId {
  let hasWait = false
  let hasAi = false
  for (const it of items) {
    if (cityOf(it) !== city) continue
    const s = stationOf(it)
    if (s === "keep") return "keep"
    if (s === "wait") hasWait = true
    else if (s === "ai") hasAi = true
  }
  if (hasWait) return "wait"
  if (hasAi) return "ai"
  return "rule"
}

/** AI / 待读里的分类。规则和保留没有。 */
export type LaneId =
  | "title_drop"
  | "jd_drop"
  | "title_fail"
  | "jd_fail"
  | "click_cap"
  | "park"

export function jobKey(it: ScreenItem): string {
  return it.encryptId
}

export function stationOf(it: ScreenItem): StationId | null {
  switch (it.stage) {
    case "rule_drop":
      return "rule"
    case "ai_title_drop":
    case "ai_title_pending":
    case "ai_jd_drop":
    case "ai_jd_pending":
      return "ai"
    case "jd_park":
    case "jd_queued":
      return "wait"
    case "ai_keep":
      return "keep"
    default:
      return null
  }
}

export function laneOf(it: ScreenItem): LaneId | null {
  switch (it.stage) {
    case "ai_title_drop":
      return "title_drop"
    case "ai_jd_drop":
      return "jd_drop"
    case "ai_title_pending":
      return "title_fail"
    case "ai_jd_pending":
      return "jd_fail"
    case "jd_queued":
      return "click_cap"
    case "jd_park":
      return "park"
    default:
      return null
  }
}

export function cityOf(it: ScreenItem): CityPage | null {
  const p = it.cityPage
  if (p === "杭州" || p === "上海" || p === "其它") return p
  return null
}

export function isPlaced(it: ScreenItem): boolean {
  return Boolean(it.encryptId) && stationOf(it) != null && cityOf(it) != null
}

export function activeClass(text: string): string {
  if (!text) return "act-none"
  if (/刚刚|在线|今日|今天|[123]日|[123]天/.test(text)) return "act-hot"
  if (/本周|周内|[4567]日|[4567]天|2周/.test(text)) return "act-mid"
  return "act-cold"
}

export function bossHref(href: string): string {
  if (!href) return ""
  if (href.startsWith("http")) return href
  return `https://www.zhipin.com${href.startsWith("/") ? href : `/${href}`}`
}

function pad(value: number): string {
  return String(value).padStart(2, "0")
}

/** 批次键取本地日期，同一轮筛选的岗位共用同一个键。 */
export function batchKey(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function batchLabel(key: string): string {
  const match = /^\d{4}-(\d{2}-\d{2})$/.exec(key)
  return match ? match[1] : key
}

export function batchMoment(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ""
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function batchKeys(items: ScreenItem[]): string[] {
  const keys = new Set<string>()
  for (const item of items) {
    const key = batchKey(item.batchAt)
    if (key) keys.add(key)
  }
  return [...keys].sort((a, b) => b.localeCompare(a))
}
