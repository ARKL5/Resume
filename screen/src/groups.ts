import type { ScreenItem } from "./types"

const GROUP_RANK = [
  "HR未近3天活跃",
  "公司名含：外包",
  "公司名含：派遣",
  "公司名含：代招",
  "公司名含：驻场",
  "公司名含：猎头",
  "岗位名含：外包",
  "岗位名含：派遣",
  "岗位名含：代招",
  "岗位名含：驻场",
  "岗位名含：猎头",
  "岗位名含：招聘顾问",
  "招聘者头衔含：外包",
  "招聘者头衔含：猎头",
  "招聘者头衔含：招聘顾问",
  "职位黑名单命中",
  "公司黑名单命中",
  "招聘者黑名单命中",
  "关键词结果",
  "列表规则淘汰",
  "待人工",
  "列表CPA淘汰",
  "待点详情（其它城市）",
  "待点详情",
  "详情CPA淘汰",
  "CPA保留",
]

function rankOf(group: string): number {
  const exact = GROUP_RANK.indexOf(group)
  if (exact >= 0) return exact
  const prefix = GROUP_RANK.findIndex((g) => group.startsWith(g))
  return prefix >= 0 ? prefix : GROUP_RANK.length
}

export function reasonGroup(it: ScreenItem): string {
  const reason = (it.reason || "").trim()
  if (reason) {
    const colon = reason.indexOf("：")
    if (colon > 0 && colon <= 12) {
      const head = reason.slice(0, colon)
      if (head === "公司名含" || head === "岗位名含" || head === "招聘者头衔含") {
        const token = reason.slice(colon + 1).split(/[，、\s]/)[0] || ""
        return token ? `${head}：${token}` : head
      }
      return head
    }
    return reason.length > 36 ? reason.slice(0, 36) : reason
  }
  const status = (it.status || it.stage || "").trim()
  return status || "未写停因"
}

export function sortByReasonGroup(items: ScreenItem[]): ScreenItem[] {
  const buckets = new Map<string, ScreenItem[]>()
  for (const it of items) {
    const g = reasonGroup(it)
    const arr = buckets.get(g)
    if (arr) arr.push(it)
    else buckets.set(g, [it])
  }
  const keys = [...buckets.keys()].sort((a, b) => {
    const d = rankOf(a) - rankOf(b)
    return d !== 0 ? d : a.localeCompare(b, "zh")
  })
  const out: ScreenItem[] = []
  for (const k of keys) {
    const arr = buckets.get(k)
    if (arr) out.push(...arr)
  }
  return out
}
