import Link from "next/link"
import type { Tender } from "@/lib/api"
import { getDirectionColor } from "@/lib/direction-colors"

const STATUS_COLOR: Record<string, string> = {
  published: "text-gray-400",
  accepting: "text-emerald-500",
  closed: "text-gray-300",
  cancelled: "text-red-400",
}

const STATUS_ICON: Record<string, string> = {
  published: "○",
  accepting: "◑",
  closed: "●",
  cancelled: "✕",
}

function scoreColor(score: number): string {
  if (score >= 0.6) return "text-violet-600"
  if (score >= 0.4) return "text-violet-500"
  return "text-violet-400"
}

function fmtNmck(n: number | null): string | null {
  if (n == null) return null
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} млрд`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} М`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} К`
  return `${n}`
}

function fmtDate(s: string | null): string | null {
  if (!s) return null
  return new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })
}

export function TenderCard({ tender }: { tender: Tender }) {
  const color = STATUS_COLOR[tender.status] ?? "text-gray-400"
  const icon = STATUS_ICON[tender.status] ?? "○"
  const nmck = fmtNmck(tender.nmck)
  const deadline = fmtDate(tender.deadline_at)
  const dirColor = tender.matched_direction ? getDirectionColor(tender.matched_direction) : null

  return (
    <Link href={`/tenders/${tender.id}`} className="block group">
      <div className="flex items-center gap-4 px-6 py-4 border-b border-gray-200 hover:bg-gray-50 hover:shadow-sm transition-all duration-200">
        {/* Status icon */}
        <span className={`text-base leading-none shrink-0 w-5 text-center ${color}`}>
          {icon}
        </span>

        {/* Number */}
        <span className="text-sm text-gray-400 font-mono w-24 shrink-0 truncate tabular-nums">
          {tender.number ? tender.number.replace(/^0+/, "").slice(-8) : `#${tender.id}`}
        </span>

        {/* Title + direction badge */}
        <span className="flex-1 flex items-center gap-3 min-w-0">
          <span className="text-[15px] text-gray-700 truncate group-hover:text-[#111827] transition-all duration-200">
            {tender.title}
          </span>
          {tender.matched_direction && (
            <span className="hidden md:inline-block shrink-0 text-sm px-2.5 py-0.5 bg-violet-100 text-violet-800 border border-violet-300 font-medium max-w-[180px] truncate">
              {tender.matched_direction}
            </span>
          )}
        </span>

        {/* Right metadata */}
        <div className="flex items-center gap-6 shrink-0 text-sm text-gray-500">
          {tender.score != null && (
            <span className={`w-12 text-right font-semibold text-[15px] ${scoreColor(tender.score)}`}>
              {(tender.score * 100).toFixed(0)}%
            </span>
          )}
          <span className="hidden lg:block w-[220px] truncate text-gray-500">
            {tender.customer_name || "—"}
          </span>
          <span className="tabular-nums w-24 text-right text-gray-500">{deadline || "—"}</span>
          <span className="tabular-nums w-24 text-right text-[#111827] font-semibold">
            {nmck ? `${nmck} ₽` : "—"}
          </span>
        </div>
      </div>
    </Link>
  )
}
