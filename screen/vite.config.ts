import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import type { Connect, Plugin } from "vite"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import { fileListBody, isFileName, readConfig, resolveUnder } from "./screen-data.mjs"

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const FILE_NAME = /^(\d{8}-\d{6})_([^_]+)_(.+)\.jsonl$/

type ScreenGroup = "seen" | "archive"

function screenData(): Plugin {
  const attach = (middlewares: Connect.Server) => {
    middlewares.use((req, res, next) => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1")
      if (url.pathname === "/api/screen-files") {
        const listed = listFiles()
        if ("error" in listed) {
          send(res, 500, listed)
          return
        }
        send(res, 200, listed)
        return
      }
      if (url.pathname === "/api/screen-results") {
        send(res, ...readResults(url))
        return
      }
      next()
    })
  }
  return {
    name: "screen-data",
    configureServer(server) {
      attach(server.middlewares)
    },
    configurePreviewServer(server) {
      attach(server.middlewares)
    },
  }
}

function listFiles(): { files: Record<string, unknown>[]; archive: boolean } | { error: string } {
  const dirs = yamlDirs()
  if (dirs.error || !dirs.seen) return { error: dirs.error || "找不到结果目录" }
  const seen = describe(dirs.seen, "seen")
  const archiveFiles = dirs.archive ? describe(dirs.archive, "archive") : []
  return fileListBody(seen, archiveFiles, Boolean(dirs.archive))
}

function readResults(url: URL): [number, Record<string, unknown>] {
  const dirs = yamlDirs()
  if (dirs.error || !dirs.seen) {
    return [500, { items: [], file: "", error: dirs.error || "找不到结果目录" }]
  }
  const group = url.searchParams.get("group") === "archive" ? "archive" : "seen"
  const name = url.searchParams.get("file") ?? ""
  if (!isFileName(name)) {
    return [400, { items: [], file: name, error: "非法筛选结果文件名" }]
  }
  const dir = group === "archive" ? dirs.archive : dirs.seen
  if (!dir) {
    return [400, { items: [], file: name, error: "没有实验目录" }]
  }
  const filePath = path.join(dir, name)
  if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    return [404, { items: [], file: name, error: "找不到筛选结果" }]
  }
  const items: unknown[] = []
  const text = fs.readFileSync(filePath, "utf8")
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue
    try {
      items.push(JSON.parse(line))
    } catch {
      // 坏行跳过，和原先对照页一样
    }
  }
  return [200, { items, file: name }]
}

function yamlDirs(): { seen: string | null; archive: string | null; error?: string } {
  const yamlPath = path.join(ROOT, "boss.yaml")
  if (!fs.existsSync(yamlPath)) return { seen: null, archive: null, error: "找不到 boss.yaml" }
  const cfg = readConfig(fs.readFileSync(yamlPath, "utf8"))
  const seenDir = resolveUnder(ROOT, cfg.seen)
  if (!seenDir) return { seen: null, archive: null, error: "结果目录不合法" }
  if (!cfg.archive) return { seen: seenDir, archive: null }
  const archiveDir = resolveUnder(ROOT, cfg.archive)
  if (!archiveDir) return { seen: null, archive: null, error: "实验目录不合法" }
  return { seen: seenDir, archive: archiveDir }
}

function describe(dir: string, group: ScreenGroup): Record<string, unknown>[] {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) return []
  const out: Record<string, unknown>[] = []
  for (const name of fs.readdirSync(dir)) {
    if (!isFileName(name) || name === "opened-chats.jsonl") continue
    const filePath = path.join(dir, name)
    if (!fs.statSync(filePath).isFile()) continue
    const stat = fs.statSync(filePath)
    const text = fs.readFileSync(filePath, "utf8")
    let rows = 0
    for (const line of text.split(/\r?\n/)) {
      if (line.trim()) rows += 1
    }
    const matched = FILE_NAME.exec(name)
    out.push({
      name,
      group,
      mtime: stat.mtimeMs,
      rows,
      startedAt: matched?.[1] ?? "",
      jobType: matched?.[2] ?? "",
      keyword: matched ? matched[3].replace(/-/g, " ") : "",
    })
  }
  out.sort((a, b) => Number(b.mtime) - Number(a.mtime))
  return out
}

function send(res: Connect.ServerResponse, status: number, body: unknown) {
  res.statusCode = status
  res.setHeader("content-type", "application/json; charset=utf-8")
  res.end(JSON.stringify(body))
}

export default defineConfig({
  plugins: [react(), screenData()],
  server: {
    port: 6867,
    strictPort: true,
  },
  preview: {
    port: 6867,
    strictPort: true,
  },
})
