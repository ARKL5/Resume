export type ScreenItem = {
  encryptId?: string
  company?: string
  job?: string
  keyword?: string
  keywords?: string[]
  area?: string
  active?: string
  salary?: string
  href?: string
  jd?: string
  hasJd?: boolean
  stage?: string
  reason?: string
  cityPage?: string
}

export type BossStatus = {
  isRunning?: boolean
  isLoggedIn?: boolean
  needHuman?: boolean
  needHumanReason?: string
  message?: string
  status?: string
}

export type CityPage = "杭州" | "上海" | "其它"

export type StationId = "rule" | "ai" | "wait" | "keep"

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
      return "ai"
    case "jd_wait":
    case "jd_wait_other":
    case "ai_jd_pending":
      return "wait"
    case "ai_keep":
      return "keep"
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

export function bossHref(href?: string): string {
  if (!href) return ""
  if (href.startsWith("http")) return href
  return `https://www.zhipin.com${href.startsWith("/") ? href : `/${href}`}`
}
