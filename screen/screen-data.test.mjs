import assert from "node:assert/strict"
import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"
import test from "node:test"
import { readConfig, readResults, resolveUnder } from "./screen-data.mjs"

function fixture(t, yaml) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "screen-data-"))
  t.after(() => fs.rmSync(root, { recursive: true, force: true }))
  fs.writeFileSync(path.join(root, "boss.yaml"), yaml)
  return root
}

test("dbPath is read with YAML scalar semantics and defaults to screen-results/boss.db", () => {
  const cfg = readConfig(`dbPath: "screen\\u002dresults/boss.db"\n`)
  assert.deepEqual(cfg, { dbPath: "screen-results/boss.db" })
  assert.deepEqual(readConfig(""), { dbPath: "screen-results/boss.db" })
})

test("missing database file returns an empty item list without error", (t) => {
  const root = fixture(t, "dbPath: screen-results/boss.db\n")
  const [status, body] = readResults(root)
  assert.equal(status, 200)
  assert.deepEqual(body, { items: [] })
})

test("readResults reads jobs from SQLite ordered by updated_at descending", (t) => {
  const root = fixture(t, "dbPath: screen-results/boss.db\n")
  const dir = path.join(root, "screen-results")
  fs.mkdirSync(dir, { recursive: true })
  const dbPath = path.join(dir, "boss.db")
  const db = new DatabaseSync(dbPath)
  db.exec(`
    CREATE TABLE jobs (
      encrypt_id TEXT PRIMARY KEY,
      company TEXT NOT NULL DEFAULT '',
      job TEXT NOT NULL DEFAULT '',
      salary TEXT NOT NULL DEFAULT '',
      area TEXT NOT NULL DEFAULT '',
      city_page TEXT NOT NULL DEFAULT '其它',
      recruiter TEXT NOT NULL DEFAULT '',
      recruiter_title TEXT NOT NULL DEFAULT '',
      active TEXT NOT NULL DEFAULT '',
      href TEXT NOT NULL DEFAULT '',
      tags TEXT NOT NULL DEFAULT '',
      jd TEXT NOT NULL DEFAULT '',
      degree TEXT NOT NULL DEFAULT '',
      experience TEXT NOT NULL DEFAULT '',
      industry TEXT NOT NULL DEFAULT '',
      scale TEXT NOT NULL DEFAULT '',
      financing TEXT NOT NULL DEFAULT '',
      keyword TEXT NOT NULL DEFAULT '',
      keywords TEXT NOT NULL DEFAULT '[]',
      stage TEXT NOT NULL,
      reason TEXT NOT NULL DEFAULT '',
      first_seen_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      batch_at TEXT NOT NULL DEFAULT ''
    );
  `)
  const insert = db.prepare(`
    INSERT INTO jobs (encrypt_id, company, job, city_page, keywords, stage, reason, first_seen_at, updated_at, batch_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `)
  insert.run("old-id", "甲", "开发", "杭州", '["AI Agent"]', "jd_queued", "标题契合", "2026-04-15T01:00:00Z", "2026-04-15T01:00:00Z", "2026-04-15T09:00:00+08:00")
  insert.run("new-id", "乙", "Agent开发", "上海", '["AI Agent","RAG"]', "ai_keep", "保留评语", "2026-04-16T01:00:00Z", "2026-04-16T02:00:00Z", "2026-04-16T09:00:00+08:00")
  db.close()

  const [status, body] = readResults(root)
  assert.equal(status, 200)
  assert.equal(body.items.length, 2)
  assert.equal(body.items[0].encryptId, "new-id")
  assert.deepEqual(body.items[0].keywords, ["AI Agent", "RAG"])
  assert.equal(body.items[0].batchAt, "2026-04-16T09:00:00+08:00")
  assert.equal(body.items[1].encryptId, "old-id")
})

test("dbPath cannot leave the repo root", (t) => {
  const root = fixture(t, "dbPath: ../outside.db\n")
  assert.equal(resolveUnder(root, "../outside.db"), null)
  const [status, body] = readResults(root)
  assert.equal(status, 400)
  assert.match(body.error, /不合法/)
})
