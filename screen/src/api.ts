export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:9527"

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}
