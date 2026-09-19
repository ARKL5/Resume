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
  status?: string
  reason?: string
  keep?: boolean | null
  column?: number
  cityPage?: string
}

export type BossStatus = {
  isRunning?: boolean
  running?: boolean
  isLoggedIn?: boolean
  needHuman?: boolean
  needHumanReason?: string
  message?: string
  status?: string
}

export type CityPage = "杭州" | "上海" | "其它"

export function jobKey(it: ScreenItem): string {
  if (it.encryptId) return `id:${it.encryptId}`
  return `name:${it.company || ""}|${it.job || ""}`
}

export function columnOf(it: ScreenItem): number {
  const c = Number(it.column)
  return c >= 1 && c <= 4 ? c : 1
}

export function cityOf(it: ScreenItem): CityPage {
  const p = it.cityPage
  if (p === "杭州" || p === "上海" || p === "其它") return p
  return "其它"
}

export function bossHref(href?: string): string {
  if (!href) return ""
  if (href.startsWith("http")) return href
  return `https://www.zhipin.com${href.startsWith("/") ? href : `/${href}`}`
}
