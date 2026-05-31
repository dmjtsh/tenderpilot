"use client"

import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { client, pipelineApi, tendersApi, type PipelineStatus, type TenderDoc, type DocsResponse } from "@/lib/api"
import { X, ExternalLink, FileText, Download, Loader2 } from "lucide-react"
import { deadlineText } from "@/lib/deadline"
import Link from "next/link"
import { PipelineComments } from "./pipeline-comments"
import { PipelineActivity } from "./pipeline-activity"
import { PipelineAiSummary } from "./pipeline-ai-summary"
import { PipelineChat } from "./pipeline-chat"

const STATUS_OPTIONS: { value: PipelineStatus; label: string; className: string }[] = [
  { value: "new", label: "Новый", className: "bg-slate-100 text-slate-700 border-slate-300" },
  { value: "studying", label: "Изучаю", className: "bg-blue-50 text-blue-700 border-blue-300" },
  { value: "preparing", label: "Готовлю", className: "bg-amber-50 text-amber-700 border-amber-300" },
  { value: "submitted", label: "Подал", className: "bg-violet-50 text-violet-700 border-violet-300" },
  { value: "won", label: "Выиграл", className: "bg-green-50 text-green-700 border-green-300" },
  { value: "lost", label: "Проиграно", className: "bg-gray-100 text-gray-600 border-gray-400" },
]

const DOC_STATUS: Record<string, { label: string; className: string }> = {
  pending: { label: "Ожидает", className: "bg-gray-100 text-gray-500" },
  processing: { label: "Обработка", className: "bg-blue-50 text-blue-600" },
  done: { label: "Готов", className: "bg-green-50 text-green-600" },
  failed: { label: "Ошибка", className: "bg-red-50 text-red-600" },
  skipped: { label: "Пропущен", className: "bg-gray-100 text-gray-500" },
  cleaned: { label: "Очищен", className: "bg-amber-50 text-amber-600" },
}

const LAW_LABEL: Record<string, string> = {
  "44-ФЗ": "44-ФЗ",
  "223-ФЗ": "223-ФЗ",
  "615-ПП": "615-ПП",
  "b2b": "Коммерческий",
}

function fmt(n: number | string | null | undefined) {
  if (n == null) return "Не указано"
  const num = typeof n === "string" ? parseFloat(n) : n
  if (isNaN(num)) return "Не указано"
  return num.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + "\u00A0₽"
}


function fmtFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const TABS = [
  { id: "overview", label: "Обзор" },
  { id: "ai", label: "AI" },
  { id: "docs", label: "Документы" },
  { id: "comments", label: "Комментарии" },
  { id: "activity", label: "История" },
] as const

type TabId = typeof TABS[number]["id"]

export function PipelineSidePanel({
  entryId,
  tenderId,
  onClose,
  onStatusChange,
}: {
  entryId: number
  tenderId: number
  onClose: () => void
  onStatusChange: () => void
}) {
  const qc = useQueryClient()
  const [tab, setTab] = useState<TabId>("overview")

  const { data: entry } = useQuery({
    queryKey: ["pipeline", tenderId],
    queryFn: () => pipelineApi.byTender(tenderId),
  })

  const { data: tender } = useQuery({
    queryKey: ["tender-detail", tenderId],
    queryFn: () => tendersApi.get(tenderId),
  })

  const [downloading, setDownloading] = useState(false)

  const { data: resp } = useQuery<DocsResponse>({
    queryKey: ["tender-docs", tenderId],
    queryFn: () => tendersApi.getDocs(tenderId),
    enabled: tab === "docs",
    refetchInterval: (query) => {
      const r = query.state.data
      if (r?.downloadStatus === "downloading") return 3000
      if (downloading) return 3000
      return false
    },
  })
  const docs = resp?.docs ?? []
  const downloadStatus = resp?.downloadStatus ?? ""
  const noDocs = downloadStatus === "no_docs"

  useEffect(() => {
    if (!downloading) return
    if (downloadStatus === "no_docs" || downloadStatus === "failed") {
      setDownloading(false)
      return
    }
    if (docs.length > 0 && docs.some((d: TenderDoc) => d.parse_status === "done")) {
      setDownloading(false)
    }
  }, [downloading, docs, downloadStatus])

  const handleDownloadDocs = async () => {
    setDownloading(true)
    try {
      const res = await tendersApi.downloadDocs(tenderId)
      if (res?.no_docs) {
        setDownloading(false)
      }
    } catch {
      setDownloading(false)
    }
  }

  const updateMut = useMutation({
    mutationFn: (status: PipelineStatus) =>
      pipelineApi.update(entryId, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipeline", tenderId] })
      qc.invalidateQueries({ queryKey: ["pipeline-activity", entryId] })
      onStatusChange()
    },
  })

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handleEsc)
    return () => document.removeEventListener("keydown", handleEsc)
  }, [onClose])

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/10 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed right-0 top-0 bottom-0 w-[600px] max-w-full bg-white shadow-xl z-50 flex flex-col animate-slide-in">
        {/* Header */}
        <div className="flex items-start gap-3 px-6 py-5 border-b border-gray-200 shrink-0">
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600 mt-0.5">
            <X className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            {entry?.tender_customer_name && (
              <p className="text-sm text-gray-400 mb-1">{entry.tender_customer_name}</p>
            )}
            <p className="text-base font-semibold text-[#111827] line-clamp-2">
              {entry?.tender_title || tender?.title}
            </p>
          </div>
          <Link
            href={`/tenders/${tenderId}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-500 border border-gray-200 rounded hover:bg-gray-50 hover:text-gray-700 transition-colors shrink-0"
          >
            Открыть
            <ExternalLink className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 px-6 shrink-0">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-3 text-[15px] font-medium border-b-2 -mb-px transition-colors ${
                tab === t.id
                  ? "border-violet-600 text-violet-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
              {t.id === "docs" && docs.length > 0 && (
                <span className="ml-1.5 text-sm text-gray-400">{docs.length}</span>
              )}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {tab === "overview" && (
            <div className="flex flex-col gap-6">
              {/* Status selector */}
              <div>
                <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2.5">Статус</p>
                <div className="flex flex-wrap gap-2">
                  {STATUS_OPTIONS.map((s) => (
                    <button
                      key={s.value}
                      onClick={() => updateMut.mutate(s.value)}
                      disabled={updateMut.isPending}
                      className={`px-3 py-1.5 text-sm font-medium rounded border transition-all ${
                        entry?.status === s.value
                          ? `${s.className} border-current opacity-100`
                          : "bg-white border-gray-200 text-gray-500 opacity-60 hover:opacity-100"
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Details grid */}
              <div>
                <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2.5">Детали</p>
                <div className="grid grid-cols-2 gap-2.5">
                  <Field label="Сумма контракта" value={fmt(entry?.tender_nmck ?? tender?.nmck)} />
                  {(() => {
                    const dl = deadlineText(entry?.tender_deadline_at ?? tender?.deadline_at)
                    return <Field label="До дедлайна" value={dl.text} valueClassName={dl.className} />
                  })()}
                  <Field label="Закон" value={LAW_LABEL[entry?.tender_law_type || tender?.law_type || ""] || entry?.tender_law_type || "Не указано"} />
                  <Field label="Регион" value={entry?.tender_region || tender?.region || "Не указано"} />
                  {tender?.trading_platform && <Field label="Площадка" value={tender.trading_platform} />}
                </div>
              </div>

            </div>
          )}

          {tab === "ai" && (
            <div className="flex flex-col gap-5">
              <div className="border border-gray-200 rounded-lg p-5">
                <PipelineAiSummary tenderId={tenderId} />
              </div>
              <div className="border border-gray-200 rounded-lg p-5">
                <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Вопросы по тендеру</p>
                <PipelineChat tenderId={tenderId} />
              </div>
            </div>
          )}

          {tab === "docs" && (
            <div className="flex flex-col gap-2.5">
              {docs.length === 0 && !downloading ? (
                <div className="py-8 flex flex-col items-center gap-3">
                  {noDocs ? (
                    <p className="text-[15px] text-gray-400">Документы недоступны для этого тендера</p>
                  ) : (
                    <>
                      <p className="text-[15px] text-gray-400">Нет загруженных документов</p>
                      <button
                        onClick={handleDownloadDocs}
                        className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-[#111827] text-white hover:bg-gray-800 transition-colors rounded"
                      >
                        <Download className="w-4 h-4" />
                        Загрузить документы
                      </button>
                    </>
                  )}
                </div>
              ) : docs.length === 0 && downloading ? (
                <div className="py-8 flex flex-col items-center gap-3">
                  <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
                  <p className="text-[15px] text-gray-400">Загрузка документов...</p>
                </div>
              ) : (
                docs.map((d: TenderDoc) => {
                  const st = DOC_STATUS[d.parse_status] || DOC_STATUS.pending
                  return (
                    <div key={d.id} className="flex items-center gap-3 p-3.5 border border-gray-100 rounded hover:bg-gray-50 transition-colors">
                      <FileText className="w-5 h-5 text-gray-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-[15px] text-gray-800 truncate">{d.filename}</p>
                        <p className="text-sm text-gray-400">{fmtFileSize(d.file_size)}</p>
                      </div>
                      <span className={`px-2.5 py-1 text-sm font-medium rounded ${st.className}`}>
                        {st.label}
                      </span>
                      <button
                        onClick={async (e) => {
                          e.stopPropagation()
                          try {
                            const res = await client.get(`/tenders/${tenderId}/docs/${d.id}/download/`, { responseType: "blob" })
                            const url = window.URL.createObjectURL(res.data)
                            const a = document.createElement("a")
                            a.href = url
                            a.download = d.filename
                            a.click()
                            setTimeout(() => window.URL.revokeObjectURL(url), 5000)
                          } catch { /* ignore */ }
                        }}
                        className="p-2 rounded hover:bg-gray-200 transition-colors text-gray-400 hover:text-gray-600 shrink-0"
                        title="Скачать"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    </div>
                  )
                })
              )}
            </div>
          )}

          {tab === "comments" && <PipelineComments entryId={entryId} />}
          {tab === "activity" && <PipelineActivity entryId={entryId} />}
        </div>
      </div>

      <style jsx global>{`
        @keyframes slideIn {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        .animate-slide-in {
          animation: slideIn 0.2s ease-out;
        }
      `}</style>
    </>
  )
}

function Field({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="bg-gray-50 rounded px-3.5 py-2.5">
      <p className="text-sm text-gray-400 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-[15px] font-medium ${valueClassName || "text-[#111827]"}`}>{value}</p>
    </div>
  )
}

