import type { ScreenItem } from "./types"

export type ReasonKind = "规则" | "AI" | null
export type ReasonPhase = "标题" | "JD" | null

export function formatReason(raw: string): { kind: ReasonKind; phase: ReasonPhase; body: string } {
  const text = raw.trim()
  if (!text) return { kind: null, phase: null, body: "未写明" }
  if (text.startsWith("规则 ")) {
    return { kind: "规则", phase: null, body: text.slice(3).trim() || "未写明" }
  }
  if (text.startsWith("AI 标题 ")) {
    return { kind: "AI", phase: "标题", body: text.slice("AI 标题 ".length).trim() || "无理由" }
  }
  if (text.startsWith("AI JD ")) {
    return { kind: "AI", phase: "JD", body: text.slice("AI JD ".length).trim() || "无理由" }
  }
  return { kind: null, phase: null, body: text }
}

export function itemReason(it: ScreenItem): { kind: ReasonKind; phase: ReasonPhase; body: string } {
  return formatReason(it.reason || "")
}
