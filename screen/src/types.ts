import type { STATIONS } from "./constants"

export type Stage =
  | "rule_drop"
  | "ai_title_drop"
  | "ai_title_pending"
  | "ai_jd_drop"
  | "ai_jd_pending"
  | "jd_wait"
  | "jd_wait_other"
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
  jd?: string
  stage: Stage
  reason: string
  cityPage: CityPage
  recruiter?: string
}

export type ScreenFile = {
  name: string
  group: "seen" | "archive"
  keyword: string
  jobType: string
  startedAt: string
  rows: number
  mtime: number
}

export function fileKey(file: ScreenFile): string {
  return `${file.group}:${file.name}`
}

export function defaultScreenKey(files: ScreenFile[]): string | null {
  const seen = files.find((file) => file.group === "seen")
  return seen ? fileKey(seen) : null
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

/** AI / 待读里的分类。规则和保留没有。其它城走城市分页。 */
export type LaneId =
  | "title_drop"
  | "jd_drop"
  | "title_fail"
  | "jd_fail"
  | "click_cap"
  | "park"

export function jobKey(it: ScreenItem): string {
  if (it.encryptId) return `id:${it.encryptId}`
  return `name:${it.company || ""}|${it.job || ""}`
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
    case "jd_wait":
    case "jd_wait_other":
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
    case "jd_wait": {
      const r = it.reason || ""
      return r.includes("将点详情") || r.includes("详情上限") ? "click_cap" : "park"
    }
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
  return stationOf(it) != null && cityOf(it) != null
}

export function fileLabel(f: ScreenFile): string {
  return `${f.keyword} · ${f.jobType} · ${f.startedAt} ${f.rows}`
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
