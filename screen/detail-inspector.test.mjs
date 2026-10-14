import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { createServer } from "vite"

let server
let DetailInspector

before(async () => {
  server = await createServer({
    configFile: false,
    esbuild: { jsx: "automatic" },
    server: { middlewareMode: true },
    appType: "custom",
  })
  const module = await server.ssrLoadModule("/src/components/detail-inspector.tsx")
  DetailInspector = module.default
})

after(async () => {
  await server?.close()
})

function renderItem(overrides) {
  return renderToStaticMarkup(createElement(DetailInspector, {
    item: {
      encryptId: "plain-text-job",
      company: "示例公司",
      job: "开发实习生",
      keyword: "RAG",
      keywords: ["RAG"],
      area: "杭州",
      active: "",
      href: "",
      stage: "ai_keep",
      cityPage: "杭州",
      reason: "保留",
      ...overrides,
    },
    isStarred: false,
    onToggleStar() {},
    stationTitle: "保留",
  }))
}

test("benchmark renders technical terms as continuous original text without keyword decorations", () => {
  const benchmark = "retail-bench、rag-backend 与 tau2-bench 可对标 Agent、RAG 和 Pydantic"
  const html = renderItem({
    reason: `【职责与技术】开发工具【对标与切入】${benchmark}【公司背景】小团队【排雷风险】经验不足`,
  })

  assert.ok(html.includes(`<div class="row-body benchmark-content">${benchmark}</div>`))
  assert.ok(!html.includes("swiss-tech-token"))
})

test("JD preserves paragraphs, headings and escaped text without decorating technical terms", () => {
  const html = renderItem({
    jd: "工作职责\n开发 Agent 和 RAG，使用 Python & PostgreSQL\n\n任职要求\n熟悉 FastAPI、pgvector 与 pytest",
  })

  assert.ok(html.includes('<span class="header-title">工作职责</span>'))
  assert.ok(html.includes('<span class="header-title">任职要求</span>'))
  assert.ok(html.includes('<div class="jd-spacer"></div>'))
  assert.ok(html.includes('<div class="swiss-jd-line">开发 Agent 和 RAG，使用 Python &amp; PostgreSQL</div>'))
  assert.ok(html.includes('<div class="swiss-jd-line">熟悉 FastAPI、pgvector 与 pytest</div>'))
  assert.ok(!html.includes("swiss-tech-token"))
})
