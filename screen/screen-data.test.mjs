import assert from "node:assert/strict"
import path from "node:path"
import test from "node:test"
import { fileListBody, isFileName, readConfig, resolveUnder } from "./screen-data.mjs"

test("comment and next-line scalars match the screening yaml", () => {
  const cfg = readConfig(`
screenResultsDir: screen-experiments # 试跑
screenArchiveDir:
  "screen-experiments" # 留档
`)
  assert.equal(cfg.seen, "screen-experiments")
  assert.equal(cfg.archive, "screen-experiments")
})

test("missing archive key stays off", () => {
  const cfg = readConfig("screenResultsDir: screen-results\n")
  assert.equal(cfg.seen, "screen-results")
  assert.equal(cfg.archive, null)
})

test("archive key with no files still opens the second group", () => {
  const body = fileListBody([{ name: "a.jsonl", group: "seen" }], [], true)
  assert.equal(body.archive, true)
  assert.equal(body.files.length, 1)
  assert.equal(body.files.some((file) => file.group === "archive"), false)
})

test("result paths cannot leave the repo root", () => {
  const root = path.resolve("/repo")
  assert.equal(resolveUnder(root, "../boss.yaml"), null)
  assert.equal(resolveUnder(root, "screen-experiments"), path.resolve("/repo/screen-experiments"))
  assert.equal(isFileName("../x.jsonl"), false)
  assert.equal(isFileName("a/b.jsonl"), false)
  assert.equal(isFileName("20260922-010101_实习_A.jsonl"), true)
})
