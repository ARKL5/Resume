import fs from "node:fs"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"
import { parse } from "yaml"

export function readConfig(text) {
  const cfg = parse(text) || {}
  return {
    dbPath: cfg.dbPath || "screen-results/boss.db",
  }
}

export function resolveUnder(root, raw) {
  const name = String(raw ?? "").trim()
  if (!name || path.isAbsolute(name) || name.split(/[\\/]/).includes("..")) return null
  const target = path.resolve(root, name)
  const rel = path.relative(root, target)
  if (rel.startsWith("..") || path.isAbsolute(rel)) return null
  return target
}

export function readResults(root) {
  const cfg = readConfig(fs.readFileSync(path.join(root, "boss.yaml"), "utf8"))
  const dbPath = resolveUnder(root, cfg.dbPath)
  if (!dbPath) {
    return [400, { items: [], error: "数据库路径不合法" }]
  }
  if (!fs.existsSync(dbPath) || !fs.statSync(dbPath).isFile()) {
    return [200, { items: [] }]
  }
  const db = new DatabaseSync(dbPath)
  try {
    const table = db
      .prepare("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'jobs'")
      .get()
    if (!table) {
      return [200, { items: [] }]
    }
    const rows = db.prepare("SELECT * FROM jobs ORDER BY updated_at DESC, rowid DESC").all()
    const items = rows.map(mapRow)
    return [200, { items }]
  } finally {
    db.close()
  }
}

function mapRow(row) {
  let keywords = []
  try {
    const parsed = JSON.parse(String(row.keywords || "[]"))
    if (Array.isArray(parsed)) {
      keywords = parsed.map((k) => String(k).trim()).filter(Boolean)
    }
  } catch {
    keywords = []
  }
  return {
    encryptId: String(row.encrypt_id || ""),
    company: String(row.company || ""),
    job: String(row.job || ""),
    salary: String(row.salary || ""),
    area: String(row.area || ""),
    cityPage: String(row.city_page || "其它"),
    recruiter: String(row.recruiter || ""),
    recruiterTitle: String(row.recruiter_title || ""),
    active: String(row.active || ""),
    href: String(row.href || ""),
    tags: String(row.tags || ""),
    jd: String(row.jd || ""),
    degree: String(row.degree || ""),
    experience: String(row.experience || ""),
    industry: String(row.industry || ""),
    scale: String(row.scale || ""),
    financing: String(row.financing || ""),
    keyword: String(row.keyword || ""),
    keywords,
    stage: String(row.stage || ""),
    reason: String(row.reason || ""),
    batchAt: String(row.batch_at || ""),
  }
}
