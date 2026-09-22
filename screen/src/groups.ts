import { itemReason } from "./reason"
import type { ScreenItem } from "./types"

const GROUP_RANK = [
  "HR未近3天活跃",
  "岗位名含：运营",
  "岗位名含：标注",
  "岗位名含：训练",
  "岗位名含：销售",
  "岗位名含：客服",
  "岗位名含：前端",
  "岗位名含：客户端",
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
  "职位黑名单命中",
  "公司黑名单命中",
  "招聘者含：猎头",
  "招聘者含：招聘顾问",
  "招聘者含：驻场",
  "招聘者黑名单命中",
]

function rankOf(group: string): number {
  const exact = GROUP_RANK.indexOf(group)
  if (exact >= 0) return exact
  const prefix = GROUP_RANK.findIndex((g) => group.startsWith(g))
  return prefix >= 0 ? prefix : GROUP_RANK.length
}

export function reasonGroup(it: ScreenItem): string {
  const { body } = itemReason(it)
  const colon = body.indexOf("：")
  if (colon > 0 && colon <= 12) {
    const head = body.slice(0, colon)
    if (head === "公司名含" || head === "岗位名含" || head === "招聘者含") {
      const token = body.slice(colon + 1).split(/[，、\s]/)[0] || ""
      return token ? `${head}：${token}` : head
    }
    if (head === "HR未近3天活跃" || head.endsWith("黑名单命中")) return head
  }
  return body.length > 36 ? body.slice(0, 36) : body
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
