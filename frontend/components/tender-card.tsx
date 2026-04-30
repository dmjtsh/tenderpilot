import Link from "next/link"
import type { Tender } from "@/lib/api"

const STATUS_COLOR: Record<string, string> = {
  published: "text-muted-foreground",
  accepting: "text-emerald-400",
  closed: "text-muted-foreground/40",
  cancelled: "text-red-400/70",
}

const STATUS_ICON: Record<string, string> = {
  published: "○",
  accepting: "◑",
  closed: "●",
  cancelled: "✕",
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
  const color = STATUS_COLOR[tender.status] ?? "text-muted-foreground"
  const icon = STATUS_ICON[tender.status] ?? "○"
  const nmck = fmtNmck(tender.nmck)
  const deadline = fmtDate(tender.deadline_at)

  return (
    <Link href={`/tenders/${tender.id}`} className="block group">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border/50 hover:bg-white/[0.025] transition-colors">
        {/* Status icon */}
        <span className={`text-[13px] leading-none shrink-0 w-3.5 text-center ${color}`}>
          {icon}
        </span>

        {/* Number */}
        <span className="text-[11px] text-muted-foreground/70 font-mono w-[4.5rem] shrink-0 truncate tabular-nums">
          {tender.number ? tender.number.replace(/^0+/, "").slice(-8) : `#${tender.id}`}
        </span>

        {/* Title + direction badge */}
        <span className="flex-1 flex items-center gap-2 min-w-0">
          <span className="text-[13px] text-foreground/90 truncate group-hover:text-foreground transition-colors">
            {tender.title}
          </span>
          {tender.matched_direction && (
            <span className="hidden md:inline-block shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary/80 border border-primary/20 font-medium max-w-[140px] truncate">
              {tender.matched_direction}
            </span>
          )}
        </span>

        {/* Right metadata */}
        <div className="flex items-center gap-5 shrink-0 text-[11px] text-muted-foreground">
          {tender.score != null && (
            <span className="text-primary font-medium text-xs">
              {(tender.score * 100).toFixed(0)}%
            </span>
          )}
          {tender.law_type && (
            <span className="hidden sm:block text-[10px] px-1.5 py-0.5 rounded border border-border/60 text-muted-foreground/70 font-mono shrink-0">
              {tender.law_type}
            </span>
          )}
          {tender.trading_platform && (
            <span className="hidden xl:block text-[11px] text-muted-foreground/60 max-w-[140px] truncate shrink-0">
              {tender.trading_platform}
            </span>
          )}
          {tender.customer_name && (
            <span className="hidden lg:block max-w-[180px] truncate">
              {tender.customer_name}
            </span>
          )}
          {deadline && (
            <span className="tabular-nums w-[4.5rem] text-right">{deadline}</span>
          )}
          {nmck && (
            <span className="tabular-nums w-[4.5rem] text-right text-foreground/70 font-medium">
              {nmck} ₽
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}
