const CHROME = 140
const ROW = 52

export function colsForWidth(width: number): number {
  if (width >= 1760) return 3
  if (width >= 1000) return 2
  return 1
}

export function pageSizeForViewport(width: number, height: number): number {
  const cols = colsForWidth(width)
  const rows = Math.max(8, Math.floor((height - CHROME) / ROW))
  return cols * rows
}
