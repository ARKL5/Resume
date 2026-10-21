import assert from "node:assert/strict"
import test from "node:test"
import { STATIONS } from "./src/constants.ts"
import { parseReason } from "./src/reason.ts"
import { activeClass, batchKey, batchKeys, batchLabel, laneOf, stationOf } from "./src/types.ts"

test("station names and shortcuts share one definition", () => {
  assert.deepEqual(STATIONS.map(({ id, title, keyHint }) => [id, title, keyHint]), [
    ["keep", "保留", "1"],
    ["wait", "待读", "2"],
    ["ai", "AI", "3"],
    ["rule", "规则", "4"],
  ])
})

test("stage maps directly to station and lane without inspecting reason text", () => {
  assert.equal(stationOf({ stage: "jd_queued" }), "wait")
  assert.equal(laneOf({ stage: "jd_queued" }), "click_cap")
  assert.equal(stationOf({ stage: "jd_park" }), "wait")
  assert.equal(laneOf({ stage: "jd_park" }), "park")
  assert.equal(stationOf({ stage: "ai_keep" }), "keep")
  assert.equal(laneOf({ stage: "ai_keep" }), null)
})

test("four-part comments are split without inventing missing assessments", () => {
  const parsed = parseReason("【职责与技术】开发 Agent【对标与切入】Python 工具【公司背景】小团队【排雷风险】无明显硬伤")
  assert.deepEqual(parsed.modular, {
    dutyAndTech: "开发 Agent",
    benchmark: "Python 工具",
    companyBg: "小团队",
    risk: "无明显硬伤",
  })
  assert.equal(parsed.summarySnippet, "Python 工具")
  assert.equal(parseReason("【职责与技术】开发 Agent").modular.risk, "")
  const plain = parseReason("候选人适合做 RAG，主要风险是经验不足")
  assert.equal(plain.modular, null)
  assert.equal(plain.body, "候选人适合做 RAG，主要风险是经验不足")
})

test("both job views use the same active-time classification", () => {
  assert.equal(activeClass("刚刚活跃"), "act-hot")
  assert.equal(activeClass("本周活跃"), "act-mid")
  assert.equal(activeClass("本月活跃"), "act-cold")
})

test("one screening run is one local batch, same-day runs stay separate", () => {
  assert.equal(batchKey("2026-10-14T20:26:00"), "2026-10-14 20:26")
  assert.equal(batchKey("2026-10-14T23:59:00"), "2026-10-14 23:59")
  assert.equal(batchKey(""), "")
  assert.equal(batchKey("not-a-date"), "")
  assert.equal(batchLabel("2026-10-21 10:44"), "10-21 10:44")
  assert.equal(batchLabel("2026-10-21"), "2026-10-21")
  assert.deepEqual(
    batchKeys([
      { batchAt: "2026-10-14T20:26:00" },
      { batchAt: "2026-10-21T10:44:00" },
      { batchAt: "2026-10-21T09:10:00" },
    ]),
    ["2026-10-21 10:44", "2026-10-21 09:10", "2026-10-14 20:26"],
  )
})
