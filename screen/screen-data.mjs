import path from "node:path"

export function readConfig(text) {
  const lines = String(text).split(/\r?\n/)
  const seenRaw = readKey(lines, "screenResultsDir")
  const archiveRaw = readKey(lines, "screenArchiveDir")
  return {
    seen: seenRaw ? seenRaw : "screen-results",
    archive: archiveRaw ? archiveRaw : null,
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

export function fileListBody(seenFiles, archiveFiles, archiveEnabled) {
  return { files: [...seenFiles, ...archiveFiles], archive: Boolean(archiveEnabled) }
}

function readKey(lines, key) {
  const re = new RegExp("^" + key + ":\\s*(.*)$")
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (!line || line[0] === " " || line[0] === "\t" || line.trim().startsWith("#")) continue
    const matched = re.exec(line)
    if (!matched) continue
    const inline = stripYamlScalar(matched[1])
    if (inline) return inline
    for (let j = i + 1; j < lines.length; j++) {
      const next = lines[j]
      if (!next.trim() || next.trim().startsWith("#")) continue
      if (next[0] === " " || next[0] === "\t") return stripYamlScalar(next.trim())
      break
    }
    return ""
  }
  return null
}

function stripYamlScalar(raw) {
  const text = String(raw ?? "").trim()
  if (!text) return ""
  if (text[0] === '"' || text[0] === "'") {
    const end = text.indexOf(text[0], 1)
    if (end > 0) return text.slice(1, end)
  }
  return text.replace(/\s+#.*$/, "").trim()
}
