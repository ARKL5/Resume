import assert from "node:assert/strict"
import test from "node:test"
import { STATIONS } from "./src/constants.ts"
import { parseReason } from "./src/reason.ts"
import { activeClass, defaultScreenFile, fileKey, fileLabel } from "./src/types.ts"

test("station names and shortcuts share one definition", () => {
  assert.deepEqual(STATIONS.map(({ id, title, keyHint }) => [id, title, keyHint]), [
    ["keep", "保留", "1"],
    ["wait", "待读", "2"],
    ["ai", "AI", "3"],
    ["rule", "规则", "4"],
  ])
})

test("file keys include the group and the default file belongs to seen", () => {
  const file = {
    name: "20260922-010101_实习_AI-Agent.jsonl",
    group: "seen",
    keyword: "AI Agent",
    jobType: "实习",
    startedAt: "20260922-010101",
    rows: 5,
    mtime: 1,
  }
  const experiment = { ...file, group: "archive" }
  assert.equal(fileKey(file), `seen:${file.name}`)
  assert.equal(fileKey(experiment), `archive:${file.name}`)
  assert.equal(defaultScreenFile([experiment, file]), file)
  assert.equal(defaultScreenFile([experiment]), null)
  assert.equal(fileLabel(file), "AI Agent · 实习 · 20260922-010101 5")
})

test("four-part comments are split without inventing missing assessments", () => {
  const parsed = parseReason("AI JD 【职责与技术】开发 Agent【对标与切入】Python 工具【公司背景】小团队【排雷风险】无明显硬伤")
  assert.deepEqual(parsed.modular, {
    dutyAndTech: "开发 Agent",
    benchmark: "Python 工具",
    companyBg: "小团队",
    risk: "无明显硬伤",
  })
  assert.equal(parsed.summarySnippet, "Python 工具")
  assert.equal(parseReason("AI JD 【职责与技术】开发 Agent").modular.risk, "")
  const plain = parseReason("AI JD 候选人适合做 RAG，主要风险是经验不足")
  assert.equal(plain.modular, null)
  assert.equal(plain.body, "候选人适合做 RAG，主要风险是经验不足")
})

test("both job views use the same active-time classification", () => {
  assert.equal(activeClass("刚刚活跃"), "act-hot")
  assert.equal(activeClass("本周活跃"), "act-mid")
  assert.equal(activeClass("本月活跃"), "act-cold")
})
