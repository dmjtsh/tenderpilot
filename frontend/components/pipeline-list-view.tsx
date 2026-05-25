"use client"

import { useState } from "react"
import type { TenderPipelineEntry } from "@/lib/api"
import { ChevronDown, ChevronUp } from "lucide-react"
import { deadlineText } from "@/lib/deadline"

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  new: { label: "Новый", className: "bg-slate-100 text-slate-700" },
  studying: { label: "Изучаю", className: "bg-blue-50 text-blue-700" },
  preparing: { label: "Готовлю", className: "bg-amber-50 text-amber-700" },
  submitted: { label: "Подал", className: "bg-violet-50 text-violet-700" },
  won: { label: "Выиграл", className: "bg-green-50 text-green-700" },
  lost: { label: "Проиграно", className: "bg-gray-100 text-gray-600" },
}

const RISK_BADGE: Record<string, { label: string; className: string }> = {
  high: { label: "Высокий", className: "bg-red-50 text-red-700" },
  medium: { label: "Средний", className: "bg-amber-50 text-amber-700" },
  low: { label: "Низкий", className: "bg-green-50 text-green-700" },
}

type SortKey = "tender_nmck" | "tender_deadline_at" | "status"
type SortDir = "asc" | "desc"

const STATUS_ORDER: Record<string, number> = {
  new: 0, studying: 1, preparing: 2, submitted: 3, won: 4, lost: 5,
}

function fmt(n: number | string | null | undefined) {
  if (n == null) return "Не указано"
  const num = typeof n === "string" ? parseFloat(n) : n
  if (isNaN(num)) return "Не указано"
  return num.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + "\u00A0₽"
}


export function PipelineListView({
  entries,
  onOpen,
}: {
  entries: TenderPipelineEntry[]
  onOpen: (entry: TenderPipelineEntry) => void
}) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null)
  const [sortDir, setSortDir] = useState<SortDir>("asc")

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("asc")
    }
  }

  const sorted = [...entries].sort((a, b) => {
    if (!sortKey) return 0
    const dir = sortDir === "asc" ? 1 : -1
    if (sortKey === "tender_nmck") {
      return ((Number(a.tender_nmck) || 0) - (Number(b.tender_nmck) || 0)) * dir
    }
    if (sortKey === "tender_deadline_at") {
      const da = a.tender_deadline_at || ""
      const db = b.tender_deadline_at || ""
      return da.localeCompare(db) * dir
    }
    if (sortKey === "status") {
      return ((STATUS_ORDER[a.status] || 0) - (STATUS_ORDER[b.status] || 0)) * dir
    }
    return 0
  })

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return null
    return sortDir === "asc"
      ? <ChevronUp className="w-3 h-3 inline ml-0.5" />
      : <ChevronDown className="w-3 h-3 inline ml-0.5" />
  }

  return (
    <div className="bg-white border border-gray-200 overflow-hidden">
      <div className="grid grid-cols-[2fr_1.5fr_1fr_100px_100px_80px] gap-0 px-4 py-2.5 border-b border-gray-200 bg-gray-50">
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Название</span>
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Заказчик</span>
        <button onClick={() => handleSort("tender_nmck")} className="text-xs font-semibold text-gray-500 uppercase tracking-wide text-left">
          Сумма <SortIcon col="tender_nmck" />
        </button>
        <button onClick={() => handleSort("tender_deadline_at")} className="text-xs font-semibold text-gray-500 uppercase tracking-wide text-left">
          Дедлайн <SortIcon col="tender_deadline_at" />
        </button>
        <button onClick={() => handleSort("status")} className="text-xs font-semibold text-gray-500 uppercase tracking-wide text-left">
          Статус <SortIcon col="status" />
        </button>
        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Риск</span>
      </div>
      {sorted.map((entry) => {
        const sb = STATUS_BADGE[entry.status]
        const rb = entry.tender_overall_risk ? RISK_BADGE[entry.tender_overall_risk] : null
        return (
          <div
            key={entry.id}
            onClick={() => onOpen(entry)}
            className="grid grid-cols-[2fr_1.5fr_1fr_100px_100px_80px] gap-0 px-4 py-3 border-b border-gray-100 items-center cursor-pointer hover:bg-gray-50 transition-colors"
          >
            <div className="pr-3">
              <p className="text-sm font-medium text-[#111827] line-clamp-1">{entry.tender_title}</p>
            </div>
            <p className="text-sm text-gray-500 truncate pr-3">{entry.tender_customer_name || "Не указано"}</p>
            <p className="text-sm font-semibold text-[#111827]">{fmt(entry.tender_nmck)}</p>
            {(() => {
              const dl = deadlineText(entry.tender_deadline_at)
              return <p className={`text-sm ${dl.className}`}>{dl.text}</p>
            })()}
            <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded w-fit ${sb?.className}`}>
              {sb?.label}
            </span>
            {rb ? (
              <span className={`inline-block px-2 py-0.5 text-xs font-medium rounded w-fit ${rb.className}`}>
                {rb.label}
              </span>
            ) : (
              <span className="text-xs text-gray-300">—</span>
            )}
          </div>
        )
      })}
      {sorted.length === 0 && (
        <div className="px-4 py-8 text-center text-sm text-gray-400">Ничего не найдено</div>
      )}
    </div>
  )
}
