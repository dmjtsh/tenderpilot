"use client"

import { useEffect, useRef, useState } from "react"
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
          w-full h-8 px-2.5 text-xs font-medium border transition-colors flex items-center justify-between gap-1
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
          className="absolute top-full left-0 mt-1 w-36 bg-white border border-gray-200 shadow-lg z-50 py-1"
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

export function TenderCard({ tender, pipelineStatus, pipelineEntryId, onSetPipelineStatus, onRemoveFromPipeline }: TenderCardProps) {
  const color = STATUS_COLOR[tender.status] ?? "text-gray-400"
  const icon = STATUS_ICON[tender.status] ?? "○"
  const nmck = fmtNmck(tender.nmck)
  const deadline = fmtDate(tender.deadline_at)
  const procBadge = tender.procedure_type ? PROCEDURE_BADGE[tender.procedure_type] : null

  return (
    <Link href={`/tenders/${tender.id}`} className="block group">
      <div className="flex items-center gap-4 px-6 py-4 border-b border-gray-200 hover:bg-gray-50 hover:shadow-sm transition-all duration-200">
        {/* Status icon */}
        <span className={`text-base leading-none shrink-0 w-5 text-center ${color}`}>
          {icon}
        </span>

        {/* Title + badges */}
        <span className="flex-1 flex items-center gap-3 min-w-0">
          <span className="text-[15px] text-gray-700 truncate group-hover:text-[#111827] transition-all duration-200">
            {tender.title}
          </span>
          {procBadge && (
            <span className={`hidden md:inline-block shrink-0 text-xs px-2 py-0.5 font-medium ${procBadge.cls}`}>
              {procBadge.label}
            </span>
          )}
          {tender.matched_direction && (
            <span className="hidden md:inline-block shrink-0 text-sm px-2.5 py-0.5 bg-violet-100 text-violet-800 border border-violet-300 font-medium max-w-[180px] truncate">
              {tender.matched_direction}
            </span>
          )}
        </span>

        {/* Stage column */}
        {onSetPipelineStatus && (
          <StageDropdown
            pipelineStatus={pipelineStatus}
            pipelineEntryId={pipelineEntryId}
            tenderId={tender.id}
            onSetPipelineStatus={onSetPipelineStatus}
            onRemoveFromPipeline={onRemoveFromPipeline}
          />
        )}

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
