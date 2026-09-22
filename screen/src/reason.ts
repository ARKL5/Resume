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
  raw: string
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
      raw: "",
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
  const noteMatch = remaining.match(/[；;]\s*(本轮详情上限|将点详情|其它城不点.*)$/)
  if (noteMatch) {
    note = noteMatch[1].trim()
    remaining = remaining.slice(0, noteMatch.index).trim()
  }

  // 1. 尝试匹配标准的四维评语规范：【职责与技术】...【对标与切入】...【公司背景】...【排雷风险】...
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
        risk: risk || "无明显硬伤",
      }
    }
  }

  // 2. 尝试兼容早期非标准括号的旧版保留评语
  if (!modular && phase === "JD" && (remaining.includes("与候选人") || remaining.includes("风险："))) {
    let riskPart = ""
    let rest = remaining
    const riskIdx = remaining.indexOf("风险：") !== -1 ? remaining.indexOf("风险：") : remaining.indexOf("风险:")
    if (riskIdx !== -1) {
      riskPart = remaining.slice(riskIdx + 3).trim()
      rest = remaining.slice(0, riskIdx).trim()
    }

    const sentences = rest.split(/[。]/).map((s) => s.trim()).filter(Boolean)
    let benchPart = ""
    let compPart = ""
    const dutySentences: string[] = []

    for (const s of sentences) {
      if (s.includes("与候选人") || s.includes("匹配") || s.includes("契合")) {
        benchPart += (benchPart ? "。" : "") + s
      } else if (s.startsWith("公司") || s.includes("融资") || s.includes("0-20人") || s.includes("规模")) {
        compPart += (compPart ? "。" : "") + s
      } else {
        dutySentences.push(s)
      }
    }

    modular = {
      dutyAndTech: dutySentences.join("。") || rest,
      benchmark: benchPart,
      companyBg: compPart,
      risk: riskPart || "无明显硬伤",
    }
  }

  // 3. 尝试匹配淘汰类别 【学历硬伤】/【假Agent纯前端】等
  let dropCategory: string | null = null
  let dropEvidence: string | null = null
  const catMatch = remaining.match(/^(?:AI\s+)?【([^】]+)】(.*)$/)
  if (catMatch) {
    dropCategory = catMatch[1].trim()
    dropEvidence = catMatch[2].replace(/^[：:\s]+/, "").trim()
  }

  // 4. 生成左侧列表高密度摘要
  let summarySnippet = remaining
  if (modular) {
    summarySnippet = modular.benchmark || modular.dutyAndTech || remaining
  } else if (dropCategory) {
    summarySnippet = dropEvidence ? `【${dropCategory}】${dropEvidence}` : `【${dropCategory}】`
  }

  return {
    kind,
    phase,
    raw: text,
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
