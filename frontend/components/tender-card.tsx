"use client"

import { useEffect, useRef, useState, type ReactNode } from "react"
import Link from "next/link"
import type { Tender, PipelineStatus } from "@/lib/api"
import { ChevronDown } from "lucide-react"

const PROCEDURE_BADGE: Record<string, { label: string; cls: string }> = {
  auction: { label: "Аукцион", cls: "bg-gray-100 text-gray-600" },
  contest: { label: "Конкурс", cls: "bg-emerald-50 text-emerald-700" },
  request_quotations: { label: "Запрос котировок", cls: "bg-blue-50 text-blue-700" },
  request_proposals: { label: "Запрос предложений", cls: "bg-sky-50 text-sky-700" },
  single_source: { label: "Ед. поставщик", cls: "bg-violet-50 text-violet-700" },
}

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  bidzaar: { label: "Bidzaar B2B", cls: "bg-amber-50 text-amber-700 border border-amber-200" },
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

function fmtShortDate(s: string | null): string | null {
  if (!s) return null
  return new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })
}

function daysUntilDeadline(s: string | null): { text: string; urgent: boolean } | null {
  if (!s) return null
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const deadline = new Date(s)
  deadline.setHours(0, 0, 0, 0)
  const diff = Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
  if (diff < 0) return { text: "Истёк", urgent: true }
  if (diff === 0) return { text: "Сегодня", urgent: true }
  if (diff === 1) return { text: "1 день", urgent: true }
  if (diff <= 7) return { text: `${diff} дн.`, urgent: true }
  return { text: `${diff} дн.`, urgent: false }
}

const PIPELINE_OPTIONS: { value: PipelineStatus; label: string }[] = [
  { value: "studying", label: "Изучаю" },
  { value: "preparing", label: "Готовлю" },
  { value: "submitted", label: "Подал" },
  { value: "won", label: "Выиграл" },
  { value: "lost", label: "Проиграл" },
]

const PIPELINE_LABEL: Record<PipelineStatus, string> = Object.fromEntries(
  PIPELINE_OPTIONS.map((o) => [o.value, o.label])
) as Record<PipelineStatus, string>

interface TenderCardProps {
  tender: Tender
  pipelineStatus?: PipelineStatus | null
  pipelineEntryId?: number | null
  onSetPipelineStatus?: (tenderId: number, status: PipelineStatus, entryId?: number | null) => void
  onRemoveFromPipeline?: (entryId: number) => void
  profileId?: number | null
}

function StageDropdown({
  pipelineStatus,
  pipelineEntryId,
  tenderId,
  onSetPipelineStatus,
  onRemoveFromPipeline,
}: {
  pipelineStatus?: PipelineStatus | null
  pipelineEntryId?: number | null
  tenderId: number
  onSetPipelineStatus?: (tenderId: number, status: PipelineStatus, entryId?: number | null) => void
  onRemoveFromPipeline?: (entryId: number) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [open])

  const handleSelect = (status: PipelineStatus) => {
    setOpen(false)
    onSetPipelineStatus?.(tenderId, status, pipelineEntryId)
  }

  return (
    <div ref={ref} className="relative w-28 shrink-0">
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(!open) }}
        className={`
          w-full h-8 px-2.5 text-xs font-medium border rounded-lg transition-colors flex items-center justify-between gap-1
          ${pipelineStatus
            ? "bg-violet-50 text-violet-700 border-violet-200 hover:border-violet-300"
            : "bg-white text-gray-400 border-gray-200 hover:text-gray-600 hover:border-gray-300"
          }
        `}
      >
        <span className="truncate">{pipelineStatus ? PIPELINE_LABEL[pipelineStatus] : "Стадия"}</span>
        <ChevronDown className="w-3 h-3 shrink-0" />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 w-36 bg-white border border-gray-200 rounded-lg shadow-lg z-50 py-1"
          onClick={(e) => { e.preventDefault(); e.stopPropagation() }}
        >
          {PIPELINE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); handleSelect(opt.value) }}
              className={`
                w-full text-left px-3 py-2 text-sm transition-colors
                ${pipelineStatus === opt.value
                  ? "bg-violet-50 text-violet-700 font-medium"
                  : "text-gray-700 hover:bg-gray-50"
                }
              `}
            >
              {opt.label}
            </button>
          ))}
          {pipelineStatus && pipelineEntryId && onRemoveFromPipeline && (
            <>
              <div className="border-t border-gray-100 my-1" />
              <button
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setOpen(false); onRemoveFromPipeline(pipelineEntryId) }}
                className="w-full text-left px-3 py-2 text-sm text-red-500 hover:bg-red-50 transition-colors"
              >
                Убрать
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function LabeledValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] text-gray-400 uppercase tracking-wider leading-none mb-0.5">{label}</span>
      {children}
    </div>
  )
}

export function TenderCard({ tender, pipelineStatus, pipelineEntryId, onSetPipelineStatus, onRemoveFromPipeline, profileId }: TenderCardProps) {
  const nmck = fmtNmck(tender.nmck)
  const deadlineInfo = daysUntilDeadline(tender.deadline_at)
  const auctionDate = fmtShortDate(tender.auction_date)
  const procBadge = tender.procedure_type ? PROCEDURE_BADGE[tender.procedure_type] : null
  const sourceBadge = tender.source ? SOURCE_BADGE[tender.source] : null
  const tenderHref = profileId ? `/tenders/${tender.id}?profile_id=${profileId}` : `/tenders/${tender.id}`

  return (
    <Link href={tenderHref} className="block">
      <div className="p-5 bg-white rounded-xl border border-gray-200 hover:shadow-sm transition-all duration-200">
        {/* Row 1: Title + badges */}
        <div className="flex items-start gap-3">
          <div className="flex-1 min-w-0 text-base font-medium text-gray-900 line-clamp-2">
            {tender.title}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {sourceBadge && (
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${sourceBadge.cls}`}>
                {sourceBadge.label}
              </span>
            )}
            {procBadge && (
              <span className={`text-xs px-2 py-0.5 rounded font-medium ${procBadge.cls}`}>
                {procBadge.label}
              </span>
            )}
            {tender.matched_direction && (
              <span className="text-xs px-2 py-0.5 rounded bg-violet-100 text-violet-800 border border-violet-300 font-medium max-w-[180px] truncate">
                {tender.matched_direction}
              </span>
            )}
            {tender.score != null && (
              <span className={`text-sm font-semibold ${scoreColor(tender.score)}`}>
                {(tender.score * 100).toFixed(0)}%
              </span>
            )}
          </div>
        </div>

        {/* Row 2: Region */}
        {tender.region && (
          <div className="text-sm text-gray-500 mt-1">{tender.region}</div>
        )}

        {/* Row 3: Customer */}
        {tender.customer_name && (
          <div className="text-sm text-gray-700 line-clamp-2 mt-1">{tender.customer_name}</div>
        )}

        {/* Divider */}
        <div className="border-t border-gray-100 my-3" />

        {/* Row 4: Metrics + Stage */}
        <div className="flex items-end">
          <div className="flex items-end gap-x-5 flex-wrap gap-y-2 flex-1 min-w-0">
            {nmck && (
              <LabeledValue label="НМЦ">
                <span className="text-sm text-gray-900 font-medium">{nmck} ₽</span>
              </LabeledValue>
            )}

            {deadlineInfo && (
              <LabeledValue label="Подача заявок">
                <span className={`text-sm font-medium ${deadlineInfo.urgent ? "text-red-600" : "text-gray-900"}`}>
                  {deadlineInfo.text}
                </span>
              </LabeledValue>
            )}

            {auctionDate && (
              <LabeledValue label="Торги">
                <span className="text-sm text-gray-900 font-medium">{auctionDate}</span>
              </LabeledValue>
            )}

            {tender.trading_platform && (
              <LabeledValue label="Площадка">
                <span className="text-sm text-gray-900 font-medium">{tender.trading_platform}</span>
              </LabeledValue>
            )}
          </div>

          {onSetPipelineStatus && (
            <StageDropdown
              pipelineStatus={pipelineStatus}
              pipelineEntryId={pipelineEntryId}
              tenderId={tender.id}
              onSetPipelineStatus={onSetPipelineStatus}
              onRemoveFromPipeline={onRemoveFromPipeline}
            />
          )}
        </div>
      </div>
    </Link>
  )
}
