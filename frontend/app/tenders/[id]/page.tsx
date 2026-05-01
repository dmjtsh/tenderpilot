"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter, useParams } from "next/navigation"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { client, tendersApi, type Tender, type TenderSummary, type TenderDoc, type TenderQASource } from "@/lib/api"
import { AlertTriangle, Check, ChevronLeft, Download, ExternalLink, FileText, Loader2, Minus, Send, Sparkles, XCircle } from "lucide-react"
import Link from "next/link"

const STATUS_LABEL: Record<string, string> = {
  published: "Опубликован",
  accepting: "Приём заявок",
  closed: "Закрыт",
  cancelled: "Отменён",
}

const STATUS_DOT: Record<string, string> = {
  published: "bg-muted-foreground",
  accepting: "bg-emerald-400",
  closed: "bg-muted-foreground/30",
  cancelled: "bg-red-400/70",
}

function fmt(n: number | null) {
  if (n == null) return "—"
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency: "RUB", maximumFractionDigits: 0 }).format(n)
}

function fmtDate(s: string | null) {
  if (!s) return "—"
  return new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
}

const URGENCY_BADGE: Record<string, string> = {
  low: "bg-secondary text-secondary-foreground",
  medium: "bg-yellow-500/15 text-yellow-400",
  high: "bg-orange-500/15 text-orange-400",
  critical: "bg-red-500/15 text-red-400",
}

const URGENCY_LABEL: Record<string, string> = {
  low: "Не срочно",
  medium: "Умеренно",
  high: "Срочно",
  critical: "Критично",
}

const VERDICT_BADGE: Record<string, string> = {
  go: "bg-emerald-500/15 text-emerald-400",
  maybe: "bg-yellow-500/15 text-yellow-400",
  pass: "bg-red-500/15 text-red-400",
}

const VERDICT_LABEL: Record<string, string> = {
  go: "Участвовать",
  maybe: "Рассмотреть",
  pass: "Пропустить",
}

function SummaryBlock({ s }: { s: TenderSummary }) {
  return (
    <div className="space-y-4">
      {/* Verdict + has_docs badge */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${VERDICT_BADGE[s.verdict] ?? "bg-secondary text-secondary-foreground"}`}>
          {VERDICT_LABEL[s.verdict] ?? s.verdict}
        </span>
        {s.has_docs && (
          <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400">
            <FileText className="w-3 h-3" />
            На основе документов
          </span>
        )}
        {s.tender_type && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground">
            {s.tender_type}
          </span>
        )}
        <span className="text-xs text-muted-foreground">{s.verdict_reason}</span>
      </div>

      {/* Essence */}
      <p className="text-sm leading-relaxed text-foreground/80">{s.essence}</p>

      {/* Requirements */}
      {s.requirements?.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-1.5">Требования</p>
          <ul className="space-y-1">
            {s.requirements.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-foreground/75">
                <span className="text-muted-foreground/50 mt-0.5 shrink-0">·</span>
                {r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Finances */}
      {s.finances && (
        <div>
          <p className="text-xs text-muted-foreground mb-1.5">Финансы</p>
          <p className="text-sm text-foreground/75">{s.finances}</p>
        </div>
      )}

      {/* Deadline urgency */}
      <div className="flex items-center gap-2">
        <span className={`text-xs px-2 py-0.5 rounded-full ${URGENCY_BADGE[s.urgency] ?? "bg-secondary text-secondary-foreground"}`}>
          {URGENCY_LABEL[s.urgency] ?? s.urgency}
        </span>
        {s.days_left != null && (
          <span className="text-xs text-muted-foreground">{s.days_left} дней до дедлайна</span>
        )}
        {s.execution_period && (
          <span className="text-xs text-muted-foreground">· Срок: {s.execution_period}</span>
        )}
      </div>

      {/* Red flags */}
      {s.red_flags?.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground mb-1.5">Красные флаги</p>
          <ul className="space-y-1">
            {s.red_flags.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-amber-400/90">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
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
  pending: <div className="w-3.5 h-3.5 rounded-full border border-muted-foreground/30" />,
  processing: <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />,
  done: <Check className="w-3.5 h-3.5 text-emerald-400" />,
  failed: <XCircle className="w-3.5 h-3.5 text-red-400" />,
  skipped: <Minus className="w-3.5 h-3.5 text-yellow-400" />,
  cleaned: <Minus className="w-3.5 h-3.5 text-muted-foreground/30" />,
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
    <div className="flex items-center gap-3 py-2 px-3 rounded-md hover:bg-secondary/50 transition-colors">
      {DOC_STATUS_ICON[doc.parse_status] ?? DOC_STATUS_ICON.pending}
      <FileText className="w-3.5 h-3.5 text-muted-foreground/50 shrink-0" />
      <div className="flex flex-col min-w-0 flex-1">
        <span className="text-sm text-foreground/80 truncate">{doc.filename}</span>
        {doc.archive_name && (
          <span className="text-[10px] text-muted-foreground/50 truncate">из {doc.archive_name}</span>
        )}
      </div>
      {doc.is_scanned && (
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-yellow-500/15 text-yellow-400">Скан</span>
      )}
      <span className="text-[10px] text-muted-foreground/50 tabular-nums">{fmtSize(doc.file_size)}</span>
      <button
        onClick={handleDownloadFile}
        className="text-muted-foreground/40 hover:text-muted-foreground transition-colors shrink-0"
        title="Скачать"
      >
        <Download className="w-3.5 h-3.5" />
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
    <div className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Документы</p>
        {docs.length > 0 && (
          <span className="text-[10px] text-muted-foreground/50">{docs.length}</span>
        )}
        {docs.length > 0 && !isProcessing && !downloading && (
          <button
            onClick={handleDownload}
            className="text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          >
            обновить
          </button>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
        </div>
      ) : docs.length === 0 && !downloading ? (
        <button
          onClick={handleDownload}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
        >
          <Download className="w-4 h-4 group-hover:text-primary transition-colors" />
          Загрузить документы
        </button>
      ) : (
        <div className="rounded-lg border border-border bg-card/50 overflow-hidden divide-y divide-border/50">
          {downloading && docs.length === 0 && (
            <div className="flex items-center gap-2 px-3 py-2.5 text-sm text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
              Загружаем документы с ЕИС...
            </div>
          )}
          {docs.map((doc) => (
            <DocRow key={doc.id} doc={doc} tenderId={tenderId} />
          ))}
        </div>
      )}
    </div>
  )
}

function DocsProgressInline({ docs, downloading, tenderId }: { docs: TenderDoc[]; downloading: boolean; tenderId: number }) {
  if (downloading && docs.length === 0) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
        Загружаем документы с ЕИС...
      </div>
    )
  }
  if (docs.length > 0) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-400" />
          Обрабатываем документы... ({docs.filter((d) => d.parse_status === "done" || d.parse_status === "skipped").length}/{docs.length})
        </div>
        <div className="rounded-lg border border-border bg-card/50 overflow-hidden divide-y divide-border/50">
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
    <div className="mb-8">
      <div className="flex items-center gap-2 mb-3">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">AI-резюме</p>
        {summary && phase === "idle" && (
          <button
            onClick={() => handleGenerate(true)}
            className="text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          >
            обновить
          </button>
        )}
      </div>

      {summary && phase === "idle" ? (
        <SummaryBlock s={summary} />
      ) : phase === "downloading" ? (
        <DocsProgressInline docs={docs} downloading={downloading} tenderId={tenderId} />
      ) : phase === "analyzing" ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          Анализируем тендер...
        </div>
      ) : error ? (
        <div className="space-y-2">
          <p className="text-sm text-red-400/80">{error}</p>
          <button
            onClick={() => handleGenerate()}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Попробовать снова
          </button>
        </div>
      ) : (
        <button
          onClick={() => handleGenerate()}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors group"
        >
          <Sparkles className="w-4 h-4 group-hover:text-primary transition-colors" />
          Сгенерировать резюме
        </button>
      )}
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
    <div className="mb-8">
      <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">Вопросы по тендеру</p>

      {noDocs ? (
        <p className="text-sm text-muted-foreground">
          Загрузите документы тендера, чтобы задавать вопросы.
        </p>
      ) : (
        <>
          {messages.length > 0 && (
            <div className="rounded-lg border border-border bg-card/50 mb-3 max-h-[400px] overflow-auto">
              <div className="divide-y divide-border/50">
                {messages.map((msg, i) => (
                  <div key={i} className="px-3 py-2.5">
                    {msg.role === "user" ? (
                      <p className="text-sm text-foreground/90 font-medium">{msg.text}</p>
                    ) : (
                      <div>
                        <p className="text-sm text-foreground/75 whitespace-pre-wrap">{msg.text}</p>
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {msg.sources.map((s, j) => (
                              <span key={j} className="text-[10px] px-1.5 py-0.5 rounded bg-secondary text-muted-foreground/60">
                                {s.filename}, фрагмент {s.chunk_index}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
                {loading && (
                  <div className="px-3 py-2.5 flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Ищем в документах...
                  </div>
                )}
              </div>
              <div ref={messagesEndRef} />
            </div>
          )}

          <div className="flex gap-2">
            <input
              type="text"
              className="flex-1 h-8 bg-secondary border border-border rounded-md px-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring"
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
              className="h-8 w-8 flex items-center justify-center rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function MetaRow({ label, value, href }: { label: string; value: string; href?: string }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-border/50">
      <span className="text-xs text-muted-foreground w-28 shrink-0 pt-px">{label}</span>
      {href ? (
        <a href={href} target="_blank" rel="noopener noreferrer" className="text-sm text-primary hover:underline">
          {value}
        </a>
      ) : (
        <span className="text-sm text-foreground/90">{value}</span>
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
        <Link href="/tenders" className="text-xs text-primary hover:underline">Назад</Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Top bar */}
      <div className="h-[52px] flex items-center gap-3 px-6 border-b border-border shrink-0">
        <Link href="/tenders" className="text-muted-foreground hover:text-foreground transition-colors">
          <ChevronLeft className="w-4 h-4" />
        </Link>
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${STATUS_DOT[tender.status] ?? "bg-muted-foreground"}`} />
          <span className="text-sm font-medium truncate">{tender.title}</span>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-8">
          {/* Header */}
          <div className="mb-6">
            <div className="flex items-center gap-2 mb-2">
              <span className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground`}>
                <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[tender.status] ?? "bg-muted-foreground"}`} />
                {STATUS_LABEL[tender.status] ?? tender.status}
              </span>
              {tender.number && (
                <span className="text-xs text-muted-foreground font-mono">{tender.number}</span>
              )}
            </div>
            <h1 className="text-xl font-semibold leading-snug text-foreground">
              {tender.title}
            </h1>
          </div>

          {/* Meta */}
          <div className="mb-8 rounded-lg border border-border bg-card/50 overflow-hidden">
            {tender.law_type && (
              <MetaRow label="Тип закупки" value={tender.law_type} />
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

          {/* OKPD */}
          {tender.okpd_codes?.length > 0 && (
            <div className="mb-8">
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">ОКПД коды</p>
              <div className="flex flex-wrap gap-1.5">
                {tender.okpd_codes.map((code) => (
                  <span
                    key={code}
                    className="text-xs px-2 py-0.5 rounded-md bg-secondary text-secondary-foreground font-mono"
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
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Открыть на ЕИС
          </a>
        </div>
      </div>
    </div>
  )
}
