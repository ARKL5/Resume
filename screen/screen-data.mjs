import fs from "node:fs"
import path from "node:path"
import { parse } from "yaml"

const FILE_NAME = /^(\d{8}-\d{6})_([^_]+)_(.+)\.jsonl$/

export function readConfig(text) {
  const cfg = parse(text)
  return {
    seen: cfg.screenResultsDir || "screen-results",
    archive: cfg.screenArchiveDir || null,
  }
}

export function resolveUnder(root, raw) {
  const name = String(raw ?? "").trim()
  if (!name || path.isAbsolute(name) || name.split(/[\\/]/).includes("..")) return null
  const dir = path.resolve(root, name)
  const rel = path.relative(root, dir)
  if (rel.startsWith("..") || path.isAbsolute(rel)) return null
  return dir
}

export function isFileName(name) {
  return typeof name === "string" && name.endsWith(".jsonl") && !name.includes("..") && !/[\\/]/.test(name)
}

export function listFiles(root) {
  const dirs = yamlDirs(root)
  const seen = describe(dirs.seen, "seen")
  const archive = dirs.archive ? describe(dirs.archive, "archive") : []
  return { files: [...seen, ...archive], archive: Boolean(dirs.archive) }
}

export function readResults(root, url) {
  const dirs = yamlDirs(root)
  const group = url.searchParams.get("group")
  const name = url.searchParams.get("file") ?? ""
  if (group !== "seen" && group !== "archive") {
    return [400, { items: [], file: name, error: "非法结果分组" }]
  }
  if (!isFileName(name)) {
    return [400, { items: [], file: name, error: "非法筛选结果文件名" }]
  }
  const dir = dirs[group]
  if (!dir) return [400, { items: [], file: name, error: "没有实验目录" }]
  const filePath = path.join(dir, name)
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return [404, { items: [], file: name, error: "找不到筛选结果" }]
  }
  const items = fs.readFileSync(filePath, "utf8")
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line))
  return [200, { items, file: name }]
}

function yamlDirs(root) {
  const cfg = readConfig(fs.readFileSync(path.join(root, "boss.yaml"), "utf8"))
  const seen = resolveUnder(root, cfg.seen)
  if (!seen) throw new Error("结果目录不合法")
  const archive = cfg.archive ? resolveUnder(root, cfg.archive) : null
  if (cfg.archive && !archive) throw new Error("实验目录不合法")
  return { seen, archive }
}

function describe(dir, group) {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return []
  const out = []
  for (const name of fs.readdirSync(dir)) {
    const matched = FILE_NAME.exec(name)
    if (!isFileName(name) || !matched) continue
    const filePath = path.join(dir, name)
    const stat = fs.statSync(filePath)
    if (!stat.isFile()) continue
    const text = fs.readFileSync(filePath, "utf8")
    out.push({
      name,
      group,
      mtime: stat.mtimeMs,
      rows: text.split(/\r?\n/).filter((line) => line.trim()).length,
      startedAt: matched[1],
      jobType: matched[2],
      keyword: matched[3].replace(/-/g, " "),
    })
  }
  out.sort((a, b) => b.mtime - a.mtime)
  return out
}
