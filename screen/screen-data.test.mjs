import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { isFileName, listFiles, readConfig, readResults, resolveUnder } from "./screen-data.mjs"

function fixture(t, yaml) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "screen-data-"))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  fs.writeFileSync(path.join(root, "boss.yaml"), yaml)
  return root
}

test("result directories are read with YAML scalar semantics", () => {
  const cfg = readConfig(`
screenResultsDir: "screen\\u002dresults" # 已筛
screenArchiveDir:
  'screen-experiments' # 实验
`)
  assert.deepEqual(cfg, { seen: "screen-results", archive: "screen-experiments" })
  assert.deepEqual(readConfig("screenResultsDir: null\n"), { seen: "screen-results", archive: null })
})

test("an empty experiment directory remains a configured second group", (t) => {
  const root = fixture(t, "screenResultsDir: screen-results\nscreenArchiveDir: screen-experiments\n")
  fs.mkdirSync(path.join(root, "screen-results"))
  fs.mkdirSync(path.join(root, "screen-experiments"))
  fs.writeFileSync(path.join(root, "screen-results", "20260922-010101_实习_A.jsonl"), "{}\n")
  const body = listFiles(root)
  assert.equal(body.archive, true)
  assert.equal(body.files.length, 1)
  assert.equal(body.files[0].group, "seen")
})

test("file listing supplies metadata and results come from the selected group", (t) => {
  const root = fixture(t, "screenResultsDir: screen-results\nscreenArchiveDir: screen-experiments\n")
  const name = "20260922-010101_实习_AI-Agent.jsonl"
  const seenRow = { encryptId: "seen-id", stage: "ai_keep", cityPage: "杭州" }
  const archiveRow = { encryptId: "experiment-id", stage: "jd_wait", cityPage: "上海" }
  for (const [dir, row] of [["screen-results", seenRow], ["screen-experiments", archiveRow]]) {
    fs.mkdirSync(path.join(root, dir))
    fs.writeFileSync(path.join(root, dir, name), JSON.stringify(row) + "\n")
  }
  const files = listFiles(root).files
  assert.equal(files.length, 2)
  assert.deepEqual(files.map((f) => f.group), ["seen", "archive"])
  const { mtime, ...file } = files[0]
  assert.equal(typeof mtime, "number")
  assert.deepEqual(file, { name, group: "seen", rows: 1, startedAt: "20260922-010101", jobType: "实习", keyword: "AI Agent" })
  const [status, body] = readResults(root, new URL(`http://localhost/api/screen-results?group=archive&file=${name}`))
  assert.equal(status, 200)
  assert.deepEqual(body.items, [archiveRow])
})

test("result paths cannot leave the repo root", () => {
  const root = path.resolve("/repo")
  assert.equal(resolveUnder(root, "../boss.yaml"), null)
  assert.equal(resolveUnder(root, "screen-experiments"), path.resolve("/repo/screen-experiments"))
  assert.equal(isFileName("../x.jsonl"), false)
  assert.equal(isFileName("a/b.jsonl"), false)
  assert.equal(isFileName("20260922-010101_实习_A.jsonl"), true)
})
