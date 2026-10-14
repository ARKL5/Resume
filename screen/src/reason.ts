import type { ScreenItem } from "./types"

export type ModularKeep = {
  dutyAndTech: string
  benchmark: string
  companyBg: string
  risk: string
}

export type ParsedReason = {
  body: string
  modular: ModularKeep | null
  dropCategory: string | null
  dropEvidence: string | null
  summarySnippet: string
}

export function parseReason(raw: string): ParsedReason {
  const remaining = (raw || "").trim()
  if (!remaining) {
    return {
      body: "未写明",
      modular: null,
      dropCategory: null,
      dropEvidence: null,
      summarySnippet: "未写明理由",
    }
  }

  // 四维评语：【职责与技术】...【对标与切入】...【公司背景】...【排雷风险】...
  let modular: ModularKeep | null = null
  if (remaining.includes("【职责与技术】") || remaining.includes("【对标与切入】")) {
    const extract = (tag: string, nextTags: string[]): string => {
      const idx = remaining.indexOf(tag)
      if (idx === -1) return ""
      const start = idx + tag.length
      let end = remaining.length
      for (const next of nextTags) {
        const nIdx = remaining.indexOf(next, start)
        if (nIdx !== -1 && nIdx < end) {
          end = nIdx
        }
      }
      return remaining.slice(start, end).replace(/^[：:\s]+/, "").trim()
    }

    const duty = extract("【职责与技术】", ["【对标与切入】", "【公司背景】", "【排雷风险】"])
    const bench = extract("【对标与切入】", ["【公司背景】", "【排雷风险】"])
    const comp = extract("【公司背景】", ["【排雷风险】"])
    const risk = extract("【排雷风险】", [])

    if (duty || bench) {
      modular = {
        dutyAndTech: duty,
        benchmark: bench,
        companyBg: comp,
        risk,
      }
    }
  }

  // 淘汰类别 【学历硬伤】/【假Agent纯前端】等
  let dropCategory: string | null = null
  let dropEvidence: string | null = null
  const catMatch = remaining.match(/^【([^】]+)】(.*)$/)
  if (!modular && catMatch) {
    dropCategory = catMatch[1].trim()
    dropEvidence = catMatch[2].replace(/^[：:\s]+/, "").trim()
  }

  // 左侧列表摘要
  let summarySnippet = remaining
  if (modular) {
    summarySnippet = modular.benchmark || modular.dutyAndTech || remaining
  } else if (dropCategory) {
    summarySnippet = dropEvidence ? `【${dropCategory}】${dropEvidence}` : `【${dropCategory}】`
  }

  return {
    body: remaining || "无理由",
    modular,
    dropCategory,
    dropEvidence,
    summarySnippet,
  }
}

export function itemReason(it: ScreenItem): ParsedReason {
  return parseReason(it.reason || "")
}
