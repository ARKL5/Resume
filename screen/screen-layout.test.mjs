import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const css = readFileSync(new URL("./src/index.css", import.meta.url), "utf8")

function rule(selector) {
  const pattern = new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*\\{([^}]+)\\}`)
  const match = css.match(pattern)
  assert.ok(match, `missing rule ${selector}`)
  return match[1]
}

test("labels stay on one line and the top bar splits before 1280px", () => {
  assert.match(rule(".swiss-segment-btn"), /white-space:\s*nowrap/)
  assert.match(rule(".swiss-tool-btn"), /white-space:\s*nowrap/)
  assert.match(css, /@media \(max-width: 1280px\) \{[\s\S]*?\.topbar-line-break\s*\{[^}]*flex:\s*1 0 100%/)
  assert.match(css, /@media \(max-width: 1280px\) \{[\s\S]*?\.swiss-search-wrap\s*\{[^}]*flex:\s*1 1 220px/)
})

test("comment titles move above the text at 1024px", () => {
  assert.match(css, /@media \(max-width: 1024px\) \{[\s\S]*?\.dossier-row\s*\{[^}]*grid-template-columns:\s*1fr/)
})

test("activity stays gray and list reasons show two lines", () => {
  assert.doesNotMatch(rule(".card-active-tag"), /swiss-red|swiss-blue/)
  assert.doesNotMatch(rule(".meta-block.active-block"), /swiss-red|swiss-blue/)
  assert.match(rule(".card-snippet-text"), /-webkit-line-clamp:\s*2/)
  assert.match(rule(".kb-hint"), /font-size:\s*12px/)
  assert.match(rule(".seg-num"), /font-size:\s*12px/)
  assert.match(rule(".card-area"), /color:\s*var\(--ink-secondary\)/)
})
