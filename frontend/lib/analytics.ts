declare global {
  interface Window {
    ym?: (id: number, action: string, goal?: string, params?: Record<string, unknown>) => void
  }
}

const YM_ID = 109470303

export function trackGoal(goalId: string) {
  if (typeof window === "undefined") return
  window.ym?.(YM_ID, "reachGoal", goalId)
}
