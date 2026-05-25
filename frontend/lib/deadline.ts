export function deadlineInfo(s: string | null | undefined): { text: string; className: string; days: number } | null {
  if (!s) return null
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const deadline = new Date(s)
  deadline.setHours(0, 0, 0, 0)
  const days = Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))

  if (days < 0) return { text: "Истёк", className: "text-red-600", days }
  if (days === 0) return { text: "Сегодня", className: "text-red-600", days }
  if (days === 1) return { text: "Завтра", className: "text-red-600", days }
  if (days <= 3) return { text: `${days} дня`, className: "text-amber-600", days }
  if (days <= 7) return { text: `${days} дней`, className: "text-yellow-600", days }
  return { text: `${days} дней`, className: "text-gray-500", days }
}

export function deadlineText(s: string | null | undefined): { text: string; className: string; days: number } {
  return deadlineInfo(s) ?? { text: "Не указано", className: "text-gray-400", days: -999 }
}
