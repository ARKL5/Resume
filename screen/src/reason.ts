import type { ScreenItem } from "./types"

export type ReasonKind = "规则" | "AI" | null
export type ReasonPhase = "标题" | "JD" | null

export type ModularKeep = {
  dutyAndTech: string
  benchmark: string
  companyBg: string
  risk: string
}

export type ParsedReason = {
  kind: ReasonKind
  phase: ReasonPhase
  body: string
  note: string | null
  modular: ModularKeep | null
  dropCategory: string | null
  dropEvidence: string | null
  summarySnippet: string
}

export function parseReason(raw: string): ParsedReason {
  const text = (raw || "").trim()
  if (!text) {
    return {
      kind: null,
      phase: null,
      body: "未写明",
      note: null,
      modular: null,
      dropCategory: null,
      dropEvidence: null,
      summarySnippet: "未写明理由",
    }
  }

  let kind: ReasonKind = null
  let phase: ReasonPhase = null
  let remaining = text

  if (remaining.startsWith("规则 ")) {
    kind = "规则"
    remaining = remaining.slice(3).trim()
  } else if (remaining.startsWith("AI 标题 ")) {
    kind = "AI"
    phase = "标题"
    remaining = remaining.slice("AI 标题 ".length).trim()
  } else if (remaining.startsWith("AI JD ")) {
    kind = "AI"
    phase = "JD"
    remaining = remaining.slice("AI JD ".length).trim()
  }

  let note: string | null = null
  const noteMatch = remaining.match(/[；;]\s*(本轮详情上限|将点详情|工作地「.+?」，本轮不点详情)$/)
  if (noteMatch) {
    note = noteMatch[1].trim()
    remaining = remaining.slice(0, noteMatch.index).trim()
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
  if (catMatch) {
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
    kind,
    phase,
    body: remaining || "无理由",
    note,
    modular,
    dropCategory,
    dropEvidence,
    summarySnippet,
  }
}

export function itemReason(it: ScreenItem): ParsedReason {
  return parseReason(it.reason || "")
}
