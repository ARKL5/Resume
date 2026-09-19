const STAR_KEY = "screen-stars:v2"
const STAR_KEY_V1 = "screen-stars"

export function loadStars(): Set<string> {
  try {
    const raw = localStorage.getItem(STAR_KEY) || localStorage.getItem(STAR_KEY_V1)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? new Set(parsed.filter((x) => typeof x === "string")) : new Set()
  } catch {
    return new Set()
  }
}

export function saveStars(stars: Set<string>) {
  try {
    localStorage.setItem(STAR_KEY, JSON.stringify([...stars]))
  } catch {
    // private mode / quota
  }
}
