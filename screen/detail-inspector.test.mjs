import assert from "node:assert/strict"
import { after, before, test } from "node:test"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { createServer } from "vite"

let server
let DetailInspector
let JobCard
let TopBar

before(async () => {
  server = await createServer({
    configFile: false,
    esbuild: { jsx: "automatic" },
    server: { middlewareMode: true },
    appType: "custom",
  })
  DetailInspector = (await server.ssrLoadModule("/src/components/detail-inspector.tsx")).default
  JobCard = (await server.ssrLoadModule("/src/components/job-card.tsx")).default
  TopBar = (await server.ssrLoadModule("/src/components/top-bar.tsx")).default
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

  assert.ok(html.includes('<span class="row-title">对标与切入点</span>'))
  assert.ok(html.includes(`<div class="row-body benchmark-content">${benchmark}</div>`))
  assert.ok(html.includes('<span class="masthead-tag status-tag">保留</span>'))
  assert.ok(html.includes('<span class="meta-block area-block">杭州</span>'))
  assert.ok(html.includes("粗筛未抓取"))
  for (const decoration of ["§", "01.1", "[核心]", "DOSSIER", "LOC:", "STATION:", "plain-text-job", "swiss-tech-token"]) {
    assert.equal(html.includes(decoration), false, decoration)
  }
})

test("drop and missing JD states keep the Chinese facts without status banners", () => {
  const dropped = renderItem({
    stage: "ai_jd_drop",
    reason: "【学历硬伤】要求硕士",
    jd: "",
    keywords: [],
  })
  assert.ok(dropped.includes('<span class="drop-category">【学历硬伤】</span>'))
  assert.ok(dropped.includes("粗筛未抓取"))
  assert.ok(dropped.includes("本岗位在列表标题粗筛阶段停驻，未发起详情页抓取请求"))
  for (const decoration of ["REJECTED", "NULL //", "FULL-TEXT", "TITLE ONLY"]) {
    assert.equal(dropped.includes(decoration), false, decoration)
  }
})

test("list reasons and navigation omit decorative prefixes but keep shortcuts and tags", () => {
  const card = renderToStaticMarkup(createElement(JobCard, {
    item: {
      encryptId: "card-job",
      company: "示例公司",
      job: "开发实习生",
      keyword: "RAG",
      keywords: ["RAG"],
      area: "杭州",
      active: "刚刚活跃",
      href: "",
      stage: "ai_keep",
      cityPage: "杭州",
      reason: "【职责与技术】开发工具【对标与切入】可对标 RAG【公司背景】小团队【排雷风险】经验不足",
    },
    index: 0,
    isSelected: false,
    isStarred: false,
    onSelect() {},
    onToggleStar() {},
  }))
  assert.ok(card.includes("可对标 RAG"))
  assert.equal(card.includes("§"), false)

  const bar = renderToStaticMarkup(createElement(TopBar, {
    totalCount: 12,
    offline: false,
    onRefresh() {},
    batches: ["2026-10-21 10:44"],
    batch: "2026-10-21 10:44",
    onSelectBatch() {},
    city: "杭州",
    onSelectCity() {},
    cityCounts: { 杭州: 8, 上海: 3, 其它: 1 },
    station: "keep",
    onSelectStation() {},
    stationCounts: { keep: 4, wait: 3, ai: 2, rule: 1 },
    lanes: [{ id: "park", title: "含糊" }],
    lane: null,
    onSelectLane() {},
    laneCounts: { park: 3 },
    query: "",
    onQueryChange() {},
    onlyStar: false,
    onToggleOnlyStar() {},
    starCount: 0,
  }))
  assert.ok(bar.includes(">杭州<"))
  assert.ok(bar.includes("[1]"))
  assert.ok(bar.includes("[刷新 r]"))
  assert.ok(bar.includes("检索岗位、公司或停因"))
  assert.ok(bar.includes(">全部<"))
  assert.ok(bar.includes("10-21 10:44"))
  for (const decoration of ["SWISS", "DB //", "01", "SUB-LANE", "FILTER", "ALL //"]) {
    assert.equal(bar.includes(decoration), false, decoration)
  }
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
