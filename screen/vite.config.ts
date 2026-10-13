import path from "node:path"
import { fileURLToPath } from "node:url"
import type { Connect, Plugin } from "vite"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import { listFiles, readResults } from "./screen-data.mjs"

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

function screenData(): Plugin {
  const attach = (middlewares: Connect.Server) => {
    middlewares.use((req, res, next) => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1")
      try {
        if (url.pathname === "/api/screen-files") {
          send(res, 200, listFiles(ROOT))
          return
        }
        if (url.pathname === "/api/screen-results") {
          const [status, body] = readResults(ROOT, url)
          send(res, status, body)
          return
        }
      } catch (error) {
        send(res, 500, { error: String(error) })
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
