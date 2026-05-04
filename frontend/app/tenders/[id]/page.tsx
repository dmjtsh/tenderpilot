"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter, useParams } from "next/navigation"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { client, tendersApi, type Tender, type TenderSummary, type TenderDoc, type TenderQASource } from "@/lib/api"
import { AlertTriangle, Check, ChevronDown, ChevronLeft, Download, ExternalLink, FileText, Loader2, Minus, Send, Sparkles, XCircle } from "lucide-react"
import Link from "next/link"
import { PipelineStatusButtons } from "@/components/pipeline-status-buttons"

const STATUS_LABEL: Record<string, string> = {
  published: "Опубликован",
  accepting: "Приём заявок",
  closed: "Закрыт",
  cancelled: "Отменён",
}

const STATUS_DOT: Record<string, string> = {
  published: "bg-gray-400",
  accepting: "bg-emerald-500",
  closed: "bg-gray-300",
  cancelled: "bg-red-400",
}

function fmt(n: number | null) {
  if (n == null) return "—"
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(n)
}

function fmtDate(s: string | null) {
  if (!s) return "—"
  return new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
}

const PROCEDURE_LABEL: Record<string, string> = {
  auction: "Электронный аукцион",
  contest: "Конкурс",
  request_quotations: "Запрос котировок",
  request_proposals: "Запрос предложений",
  single_source: "Единственный поставщик",
}

const URGENCY_BADGE: Record<string, string> = {
  low: "bg-gray-100 text-gray-600",
  medium: "bg-yellow-50 text-yellow-700",
  high: "bg-orange-50 text-orange-600",
  critical: "bg-red-50 text-red-600",
}

const URGENCY_LABEL: Record<string, string> = {
  low: "Не срочно",
  medium: "Умеренно",
  high: "Срочно",
  critical: "Критично",
}

const VERDICT_BADGE: Record<string, string> = {
  go: "bg-emerald-50 text-emerald-600",
  maybe: "bg-yellow-50 text-yellow-700",
  pass: "bg-red-50 text-red-600",
}

const VERDICT_LABEL: Record<string, string> = {
  go: "Участвовать",
  maybe: "Рассмотреть",
  pass: "Пропустить",
}

function SummaryBlock({ s }: { s: TenderSummary }) {
  return (
    <div className="space-y-5">
      {/* Verdict + has_docs badge */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`text-sm px-3 py-1 font-medium ${VERDICT_BADGE[s.verdict] ?? "bg-gray-100 text-gray-600"}`}>
          {VERDICT_LABEL[s.verdict] ?? s.verdict}
        </span>
        {s.has_docs && (
          <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 bg-blue-50 text-blue-600">
            <FileText className="w-4 h-4" />
            На основе документов
          </span>
        )}
        {s.tender_type && (
          <span className="text-sm px-3 py-1 bg-gray-100 text-gray-600">
            {s.tender_type}
          </span>
        )}
        <span className="text-sm text-gray-500">{s.verdict_reason}</span>
      </div>

      {/* Essence */}
      <p className="text-[15px] leading-relaxed text-[#111827]">{s.essence}</p>

      {/* Requirements */}
      {s.requirements?.length > 0 && (
        <div>
          <p className="text-sm font-medium text-gray-500 mb-2">Требования</p>
          <ul className="space-y-2">
            {s.requirements.map((r, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[15px] text-gray-700">
                <span className="text-gray-400 mt-0.5 shrink-0">·</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Finances */}
      {s.finances && (
        <div>
          <p className="text-sm font-medium text-gray-500 mb-2">Финансы</p>
          <p className="text-[15px] text-gray-700">{s.finances}</p>
        </div>
      )}

      {/* Deadline urgency */}
      <div className="flex items-center gap-3">
        <span className={`text-sm px-3 py-1 ${URGENCY_BADGE[s.urgency] ?? "bg-gray-100 text-gray-600"}`}>
          {URGENCY_LABEL[s.urgency] ?? s.urgency}
        </span>
        {s.days_left != null && (
          <span className="text-sm text-gray-500">{s.days_left} дней до дедлайна</span>
        )}
        {s.execution_period && (
          <span className="text-sm text-gray-500">· Срок: {s.execution_period}</span>
        )}
      </div>

      {/* Red flags */}
      {s.red_flags?.length > 0 && (
        <div>
          <p className="text-sm font-medium text-gray-500 mb-2">Красные флаги</p>
          <ul className="space-y-2">
            {s.red_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[15px] text-amber-600">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                {f}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const DOC_STATUS_ICON: Record<string, React.ReactNode> = {
  pending: <div className="w-3.5 h-3.5 rounded-full border border-gray-300" />,
  processing: <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />,
  done: <Check className="w-3.5 h-3.5 text-emerald-500" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-500" />,
  skipped: <Minus className="w-3.5 h-3.5 text-yellow-500" />,
  cleaned: <Minus className="w-3.5 h-3.5 text-gray-300" />,
}

function DocRow({ doc, tenderId }: { doc: TenderDoc; tenderId: number }) {
  async function handleDownloadFile() {
    try {
      const response = await client.get(`/tenders/${tenderId}/docs/${doc.id}/download/`, {
        responseType: "blob",
      })
      const url = window.URL.createObjectURL(response.data)
      const a = document.createElement("a")
      a.href = url
      a.download = doc.filename
      a.click()
      window.URL.revokeObjectURL(url)
    } catch { /* ignore */ }
  }

  return (
    <div className="flex items-center gap-4 py-3 px-4 hover:bg-gray-50 transition-colors">
      {DOC_STATUS_ICON[doc.parse_status] ?? DOC_STATUS_ICON.pending}
      <FileText className="w-4 h-4 text-gray-400 shrink-0" />
      <div className="flex flex-col min-w-0 flex-1">
        <span className="text-[15px] text-[#111827] truncate">{doc.filename}</span>
        {doc.archive_name && (
          <span className="text-xs text-gray-400 truncate">из {doc.archive_name}</span>
        )}
      </div>
      {doc.is_scanned && (
        <span className="text-xs px-2 py-0.5 bg-yellow-50 text-yellow-600">Скан</span>
      )}
      <span className="text-sm text-gray-400 tabular-nums">{fmtSize(doc.file_size)}</span>
      <button
        onClick={handleDownloadFile}
        className="text-gray-400 hover:text-[#111827] transition-colors shrink-0"
        title="Скачать"
      >
        <Download className="w-4 h-4" />
      </button>
    </div>
  )
}

function useDocsQuery(tenderId: number, downloading: boolean) {
  return useQuery<TenderDoc[]>({
    queryKey: ["tender-docs", tenderId],
    queryFn: () => tendersApi.getDocs(tenderId),
    refetchInterval: (query) => {
      const d = query.state.data
      if (!d || d.length === 0) return downloading ? 2000 : false
      return d.some((doc) => doc.parse_status === "pending" || doc.parse_status === "processing")
        ? 2000
        : false
    },
  })
}

function docsAreReady(docs: TenderDoc[]): boolean {
  return docs.length > 0 && docs.every((d) =>
    d.parse_status !== "pending" && d.parse_status !== "processing"
  )
}

function docsAreProcessing(docs: TenderDoc[]): boolean {
  return docs.some((d) => d.parse_status === "pending" || d.parse_status === "processing")
}

function DocumentsBlock({ tenderId }: { tenderId: number }) {
  const queryClient = useQueryClient()
  const [downloading, setDownloading] = useState(false)
  const { data: docs = [], isLoading } = useDocsQuery(tenderId, downloading)

  const isProcessing = docsAreProcessing(docs)

  async function handleDownload() {
    setDownloading(true)
    try {
      await tendersApi.downloadDocs(tenderId)
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["tender-docs", tenderId] })
      }, 1500)
    } catch {
      setDownloading(false)
    }
  }

  useEffect(() => {
    if (docs.length > 0 && !isProcessing) setDownloading(false)
  }, [docs.length, isProcessing])

  return (
    <div className="mb-8 border border-gray-200 bg-white">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200">
        <FileText className="w-5 h-5 text-gray-400" />
        <p className="text-base font-semibold text-[#111827]">Документы</p>
        {docs.length > 0 && (
          <span className="text-sm text-gray-400">{docs.length}</span>
        )}
        {docs.length > 0 && !isProcessing && !downloading && (
          <button
            onClick={handleDownload}
            className="ml-auto text-sm text-gray-400 hover:text-[#111827] transition-colors"
          >
            обновить
          </button>
        )}
      </div>

      <div className="px-6 py-5">
        {isLoading ? (
          <div className="flex items-center gap-2 text-[15px] text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : docs.length === 0 && !downloading ? (
          <button
            onClick={handleDownload}
            className="flex items-center gap-3 text-[15px] text-gray-500 hover:text-[#111827] transition-colors group"
          >
            <Download className="w-5 h-5 group-hover:text-[#111827] transition-colors" />
            Загрузить документы с ЕИС
          </button>
        ) : (
          <div className="border border-gray-200 overflow-hidden divide-y divide-gray-200">
            {downloading && docs.length === 0 && (
              <div className="flex items-center gap-3 px-4 py-3 text-[15px] text-gray-500">
                <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                Загружаем документы с ЕИС...
              </div>
            )}
            {docs.map((doc) => (
              <DocRow key={doc.id} doc={doc} tenderId={tenderId} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function DocsProgressInline({ docs, downloading, tenderId }: { docs: TenderDoc[]; downloading: boolean; tenderId: number }) {
  if (downloading && docs.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
        Загружаем документы с ЕИС...
      </div>
    )
  }
  if (docs.length > 0) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />
          Обрабатываем документы... ({docs.filter((d) => d.parse_status === "done" || d.parse_status === "skipped").length}/{docs.length})
        </div>
        <div className="rounded-lg border border-border bg-gray-50 overflow-hidden divide-y divide-border/50">
          {docs.map((doc) => (
            <DocRow key={doc.id} doc={doc} tenderId={tenderId} />
          ))}
        </div>
      </div>
    )
  }
  return null
}

type SummaryPhase = "idle" | "downloading" | "analyzing"

function AiSummaryBlock({ tenderId, initialSummary }: { tenderId: number; initialSummary: TenderSummary | null }) {
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState<TenderSummary | null>(initialSummary)
  const [phase, setPhase] = useState<SummaryPhase>("idle")
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)

  const { data: docs = [] } = useDocsQuery(tenderId, downloading)

  useEffect(() => {
    if (initialSummary) setSummary(initialSummary)
  }, [initialSummary])

  async function generateSummary() {
    setPhase("analyzing")
    setError(null)
    try {
      const data = await tendersApi.getSummary(tenderId, true)
      setSummary(data)
      setPhase("idle")
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Ошибка генерации")
      setPhase("idle")
    }
  }

  useEffect(() => {
    if (phase !== "downloading") return
    if (docsAreReady(docs)) {
      setDownloading(false)
      generateSummary()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, docs])

  async function handleGenerate(refresh = false) {
    setError(null)

    if (refresh) {
      setSummary(null)
    }

    const currentDocs = queryClient.getQueryData<TenderDoc[]>(["tender-docs", tenderId])
    const noDocs = !currentDocs || currentDocs.length === 0

    if (noDocs) {
      setPhase("downloading")
      setDownloading(true)
      try {
        await tendersApi.downloadDocs(tenderId)
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ["tender-docs", tenderId] })
        }, 1500)
      } catch {
        setError("Не удалось загрузить документы")
        setPhase("idle")
        setDownloading(false)
      }
      return
    }

    await generateSummary()
  }

  return (
    <div className="mb-8 border border-gray-200 bg-white">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200">
        <Sparkles className="w-5 h-5 text-gray-400" />
        <p className="text-base font-semibold text-[#111827]">AI-резюме</p>
        {summary && phase === "idle" && (
          <button
            onClick={() => handleGenerate(true)}
            className="ml-auto text-sm text-gray-400 hover:text-[#111827] transition-colors"
          >
            обновить
          </button>
        )}
      </div>

      <div className="px-6 py-5">
        {summary && phase === "idle" ? (
          <SummaryBlock s={summary} />
        ) : phase === "downloading" ? (
          <DocsProgressInline docs={docs} downloading={downloading} tenderId={tenderId} />
        ) : phase === "analyzing" ? (
          <div className="flex items-center gap-3 text-[15px] text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin" />
            Анализируем тендер...
          </div>
        ) : error ? (
          <div className="space-y-3">
            <p className="text-[15px] text-red-500">{error}</p>
            <button
              onClick={() => handleGenerate()}
              className="text-sm text-gray-500 hover:text-[#111827] transition-colors"
            >
              Попробовать снова
            </button>
          </div>
        ) : (
          <button
            onClick={() => handleGenerate()}
            className="flex items-center gap-3 text-[15px] text-gray-500 hover:text-[#111827] transition-colors group"
          >
            <Sparkles className="w-5 h-5 group-hover:text-[#111827] transition-colors" />
            Сгенерировать резюме
          </button>
        )}
      </div>
    </div>
  )
}

function SourceCitation({ source }: { source: TenderQASource }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = source.text.length > 200

  return (
    <div className="border-l-2 border-violet-300 bg-violet-50/30 px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-violet-700">{source.filename}</span>
        {isLong && (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="text-xs text-violet-500 hover:text-violet-700 flex items-center gap-0.5 shrink-0"
          >
            {expanded ? "Свернуть" : "Полностью"}
            <ChevronDown className={`w-3 h-3 transition-transform ${expanded ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>
      <p className={`mt-1.5 text-sm text-gray-600 italic leading-relaxed ${!expanded && isLong ? "line-clamp-3" : ""}`}>
        &laquo;{source.text}&raquo;
      </p>
    </div>
  )
}

interface ChatMessage {
  role: "user" | "assistant"
  text: string
  sources?: TenderQASource[]
}

function TenderChat({ tenderId }: { tenderId: number }) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [noDocs, setNoDocs] = useState(false)
  const [needsReindex, setNeedsReindex] = useState(false)
  const [reindexing, setReindexing] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  async function handleSend() {
    const q = input.trim()
    if (!q || loading) return

    setInput("")
    setMessages((prev) => [...prev, { role: "user", text: q }])
    setLoading(true)

    try {
      const res = await tendersApi.askQuestion(tenderId, q)
      if (!res.has_docs) {
        setNoDocs(true)
        setMessages((prev) => prev.slice(0, -1))
      } else if (res.needs_reindex) {
        setNeedsReindex(true)
        setMessages((prev) => prev.slice(0, -1))
      } else if (res.answer) {
        setMessages((prev) => [...prev, { role: "assistant", text: res.answer!, sources: res.sources }])
      } else {
        setMessages((prev) => [...prev, { role: "assistant", text: "Не удалось найти ответ в документах." }])
      }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", text: "Ошибка при получении ответа." }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="mb-8 border border-gray-200 bg-white">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200">
        <Send className="w-5 h-5 text-gray-400" />
        <p className="text-base font-semibold text-[#111827]">Вопросы по тендеру</p>
      </div>

      <div className="px-6 py-5">
        {noDocs ? (
          <p className="text-[15px] text-gray-500">
            Загрузите документы тендера, чтобы задавать вопросы.
          </p>
        ) : needsReindex ? (
          <div className="text-center py-2">
            <p className="text-[15px] text-gray-500 mb-3">
              Индекс документов устарел. Переиндексируйте для работы чата.
            </p>
            <button
              onClick={async () => {
                setReindexing(true)
                try {
                  await tendersApi.reindexDocs(tenderId)
                  setNeedsReindex(false)
                  setMessages([])
                } catch { /* ignore */ }
                setReindexing(false)
              }}
              disabled={reindexing}
              className="h-9 px-4 bg-[#111827] text-white text-sm font-medium hover:bg-[#1f2937] transition-colors disabled:opacity-50"
            >
              {reindexing ? "Переиндексация..." : "Переиндексировать документы"}
            </button>
          </div>
        ) : (
          <>
            {messages.length > 0 && (
              <div className="border border-gray-200 mb-4 max-h-[400px] overflow-auto">
                <div className="divide-y divide-gray-200">
                  {messages.map((msg, i) => (
                    <div key={i} className="px-5 py-4">
                      {msg.role === "user" ? (
                        <p className="text-[15px] text-[#111827] font-medium">{msg.text}</p>
                      ) : (
                        <div>
                          <p className="text-[15px] text-gray-700 whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                          {msg.sources && msg.sources.length > 0 && (
                            <div className="mt-3 space-y-2">
                              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Источники</p>
                              {msg.sources.map((s, j) => (
                                <SourceCitation key={j} source={s} />
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                  {loading && (
                    <div className="px-5 py-4 flex items-center gap-3 text-[15px] text-gray-500">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Ищем в документах...
                    </div>
                  )}
                </div>
                <div ref={messagesEndRef} />
              </div>
            )}

            <div className="flex gap-3">
              <input
                type="text"
                className="flex-1 h-11 bg-gray-50 border border-gray-200 px-4 text-base text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
                placeholder="Спросите о требованиях, сроках, условиях..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                maxLength={500}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className="h-11 w-11 flex items-center justify-center bg-[#111827] text-white hover:bg-[#1f2937] transition-colors disabled:opacity-40"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function MetaRow({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="flex items-start gap-4 py-3.5 px-6 border-b border-gray-200 last:border-0">
      <span className="text-[15px] text-gray-500 w-48 shrink-0">{label}</span>
      {href ? (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-[15px] text-[#111827] font-medium hover:underline">
          {value}
        </a>
      ) : (
        <span className="text-[15px] text-[#111827] font-medium">{value}</span>
      )}
    </div>
  )
}

export default function TenderDetailPage() {
  const router = useRouter()
  const { id } = useParams<{ id: string }>()
  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  const { data: tender, isLoading } = useQuery<Tender>({
    queryKey: ["tender", id],
    queryFn: () => tendersApi.get(Number(id)),
    enabled: !!id,
  })

  const initialSummary: TenderSummary | null = (() => {
    if (!tender?.ai_summary) return null
    try { return JSON.parse(tender.ai_summary) } catch { return null }
  })()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
        Загрузка...
      </div>
    )
  }

  if (!tender) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2">
        <p className="text-sm text-muted-foreground">Тендер не найден</p>
        <Link href="/tenders" className="text-xs text-violet-600 hover:underline">Назад</Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Top bar */}
      <div className="h-16 flex items-center gap-4 px-6 border-b border-gray-200 shrink-0">
        <button onClick={() => router.back()} className="h-10 px-3 flex items-center gap-1.5 text-[15px] text-gray-500 hover:text-[#111827] hover:bg-gray-100 transition-colors">
          <ChevronLeft className="w-5 h-5" />
          Назад
        </button>
        <div className="flex items-center gap-3 min-w-0">
          <span className={`w-3 h-3 rounded-full shrink-0 ${STATUS_DOT[tender.status] ?? "bg-gray-400"}`} />
          <span className="text-base font-medium truncate text-[#111827]">{tender.title}</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto animate-fade-in">
        <div className="max-w-4xl mx-auto px-6 py-10">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-3">
              <span className={`inline-flex items-center gap-2 text-sm px-3 py-1 bg-gray-100 text-gray-700`}>
                <span className={`w-2 h-2 rounded-full ${STATUS_DOT[tender.status] ?? "bg-gray-400"}`} />
                {STATUS_LABEL[tender.status] ?? tender.status}
              </span>
              {tender.number && (
                <span className="text-sm text-gray-500 font-mono">{tender.number}</span>
              )}
            </div>
            <h1 className="text-2xl font-bold leading-snug text-[#111827]">
              {tender.title}
            </h1>
          </div>

          {/* Meta */}
          <div className="mb-8 border border-gray-200 bg-white overflow-hidden">
            {tender.law_type && (
              <MetaRow label="Тип закупки" value={tender.law_type} />
            )}
            {tender.procedure_type && tender.procedure_type !== "other" && (
              <MetaRow label="Процедура" value={PROCEDURE_LABEL[tender.procedure_type] ?? tender.procedure_type} />
            )}
            <MetaRow label="НМЦК" value={fmt(tender.nmck)} />
            <MetaRow label="Регион" value={tender.region || "—"} />
            <MetaRow
              label="Площадка"
              value={tender.trading_platform_url
                ? `${tender.trading_platform || tender.trading_platform_url}`
                : tender.trading_platform || "—"}
              href={tender.trading_platform_url || undefined}
            />
            <MetaRow label="Подача заявок до" value={fmtDate(tender.deadline_at)} />
            <MetaRow
              label="Дата торгов"
              value={tender.auction_date ? fmtDate(tender.auction_date) : "—"}
            />
            <MetaRow
              label="Обеспечение заявки"
              value={
                tender.bid_security_required === false
                  ? "Не требуется"
                  : tender.bid_security_amount != null
                  ? fmt(tender.bid_security_amount)
                  : "—"
              }
            />
            <MetaRow
              label="Обеспечение контракта"
              value={
                tender.contract_security_amount != null && tender.contract_security_percent != null
                  ? `${fmt(tender.contract_security_amount)} (${tender.contract_security_percent}%)`
                  : tender.contract_security_amount != null
                  ? fmt(tender.contract_security_amount)
                  : tender.contract_security_percent != null
                  ? `${tender.contract_security_percent}%`
                  : "—"
              }
            />
            <MetaRow label="Опубликован" value={fmtDate(tender.published_at)} />
            {(tender.customer_name || tender.customer) && (
              <MetaRow
                label="Заказчик"
                value={tender.customer?.full_name ?? tender.customer_name ?? "—"}
              />
            )}
            {tender.customer?.inn && (
              <MetaRow label="ИНН заказчика" value={tender.customer.inn} />
            )}
          </div>

          {/* Pipeline status */}
          <PipelineStatusButtons tenderId={tender.id} />

          {/* OKPD */}
          {tender.okpd_codes?.length > 0 && (
            <div className="mb-8">
              <p className="text-sm font-medium text-gray-500 uppercase tracking-wide mb-3">ОКПД коды</p>
              <div className="flex flex-wrap gap-2">
                {tender.okpd_codes.map((code) => (
                  <span
                    key={code}
                    className="text-sm px-3 py-1 bg-gray-100 text-[#111827] font-mono"
                  >
                    {code}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Documents */}
          <DocumentsBlock tenderId={tender.id} />

          {/* AI summary */}
          <AiSummaryBlock tenderId={tender.id} initialSummary={initialSummary} />

          {/* Chat */}
          <TenderChat tenderId={tender.id} />

          {/* EIS link */}
          <a
            href={tender.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2.5 h-11 px-5 text-base font-medium border border-gray-200 text-gray-700 hover:text-[#111827] hover:border-gray-300 transition-colors"
          >
            <ExternalLink className="w-5 h-5" />
            Открыть на ЕИС
          </a>
        </div>
      </div>
    </div>
  )
}
