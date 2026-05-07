"use client"

import { useEffect, useRef, useState, Suspense } from "react"
import { useRouter, useParams, useSearchParams } from "next/navigation"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { client, tendersApi, profileApi, experimentsApi, type Tender, type TenderSummary, type TenderDoc, type TenderQASource, type SummaryExperimentResult, type ExperimentRun } from "@/lib/api"
import { AlertTriangle, Building2, Check, ChevronDown, ChevronLeft, ClipboardList, Download, ExternalLink, FileText, Loader2, Minus, Send, Sparkles, XCircle } from "lucide-react"
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

function fmtVolume(n: number): string {
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)} млрд ₽`
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)} млн ₽`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)} тыс ₽`
  return `${n} ₽`
}

function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-4 h-4 text-gray-400" />
      <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">{title}</span>
    </div>
  )
}

function BulletList({ items, className = "text-gray-700" }: { items: string[]; className?: string }) {
  if (!items.length) return null
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className={`flex items-start gap-2.5 text-[15px] ${className}`}>
          <span className="text-gray-400 mt-0.5 shrink-0">·</span>
          {item}
        </li>
      ))}
    </ul>
  )
}

function SummaryBlock({ s }: { s: TenderSummary }) {
  const ca = s.customer_analysis ?? { name: "", inn: "", region: "", okved_main: "", tender_count: 0, total_volume: 0, risk_assessment: "", notes: [] }
  const wd = s.work_description ?? { essence: "", payment_terms: null, execution_period: null, experience_requirements: [], deadline_info: null }
  const kr = s.key_risks ?? { certifications: [], financial_risks: [], technical_risks: [], unusual_conditions: [] }
  const rd = s.required_documents ?? { mandatory: [], optional: [], special_forms: [] }

  const hasRisks = (kr.certifications?.length ?? 0) > 0 || (kr.financial_risks?.length ?? 0) > 0 || (kr.technical_risks?.length ?? 0) > 0 || (kr.unusual_conditions?.length ?? 0) > 0
  const hasDocs = (rd.mandatory?.length ?? 0) > 0 || (rd.optional?.length ?? 0) > 0 || (rd.special_forms?.length ?? 0) > 0

  return (
    <div className="space-y-0">
      {/* Verdict badges */}
      <div className="flex items-center gap-3 flex-wrap pb-5">
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
          <span className="text-sm px-3 py-1 bg-gray-100 text-gray-600">{s.tender_type}</span>
        )}
        <span className="text-sm text-gray-500">{s.verdict_reason}</span>
      </div>

      {/* Section 1: Customer Analysis */}
      <div className="border-t border-gray-100 py-5">
        <SectionHeader icon={Building2} title="Анализ заказчика" />
        <div className="space-y-2">
          <div className="flex items-center gap-3 flex-wrap text-[15px]">
            <span className="text-[#111827] font-medium">{ca.name || "Не указан"}</span>
            {ca.inn && <span className="text-gray-400 font-mono text-sm">ИНН {ca.inn}</span>}
            {ca.region && <span className="text-gray-500">{ca.region}</span>}
          </div>
          {ca.okved_main && (
            <p className="text-sm text-gray-500">{ca.okved_main}</p>
          )}
          {ca.tender_count > 0 && (
            <p className="text-sm text-gray-500">
              {ca.tender_count} тендер{ca.tender_count === 1 ? "" : ca.tender_count < 5 ? "а" : "ов"} в базе
              {ca.total_volume > 0 && <>, общий объём {fmtVolume(ca.total_volume)}</>}
            </p>
          )}
          {ca.risk_assessment && (
            <p className="text-sm text-amber-600">{ca.risk_assessment}</p>
          )}
          <BulletList items={ca.notes ?? []} className="text-gray-500" />
        </div>
      </div>

      {/* Section 2: Work Description */}
      <div className="border-t border-gray-100 py-5">
        <SectionHeader icon={FileText} title="Описание работ" />
        <div className="space-y-3">
          <p className="text-[15px] leading-relaxed text-[#111827]">{wd.essence}</p>
          <div className="space-y-1.5">
            {wd.payment_terms && (
              <p className="text-sm text-gray-700"><span className="text-gray-400">Оплата:</span> {wd.payment_terms}</p>
            )}
            {wd.execution_period && (
              <p className="text-sm text-gray-700"><span className="text-gray-400">Срок выполнения:</span> {wd.execution_period}</p>
            )}
            {wd.deadline_info && (
              <p className="text-sm text-gray-700"><span className="text-gray-400">Подача заявки:</span> {wd.deadline_info}</p>
            )}
          </div>
          {(wd.experience_requirements?.length ?? 0) > 0 && (
            <div>
              <p className="text-sm text-gray-400 mb-1.5">Требования к опыту</p>
              <BulletList items={wd.experience_requirements} />
            </div>
          )}
        </div>
      </div>

      {/* Section 3: Key Risks */}
      {hasRisks && (
        <div className="border-t border-gray-100 py-5">
          <SectionHeader icon={AlertTriangle} title="Ключевые риски" />
          <div className="space-y-3">
            {(kr.certifications?.length ?? 0) > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-1.5">Лицензии и допуски</p>
                <BulletList items={kr.certifications} className="text-amber-600" />
              </div>
            )}
            {(kr.financial_risks?.length ?? 0) > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-1.5">Финансовые риски</p>
                <BulletList items={kr.financial_risks} className="text-amber-600" />
              </div>
            )}
            {(kr.technical_risks?.length ?? 0) > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-1.5">Технические риски</p>
                <BulletList items={kr.technical_risks} className="text-amber-600" />
              </div>
            )}
            {(kr.unusual_conditions?.length ?? 0) > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-1.5">Необычные условия</p>
                <BulletList items={kr.unusual_conditions} className="text-amber-600" />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Section 4: Required Documents */}
      {hasDocs && (
        <div className="border-t border-gray-100 py-5">
          <SectionHeader icon={ClipboardList} title="Документы для участия" />
          <div className="space-y-3">
            {(rd.mandatory?.length ?? 0) > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-1.5">Обязательные</p>
                <BulletList items={rd.mandatory} />
              </div>
            )}
            {(rd.optional?.length ?? 0) > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-1.5">Рекомендуемые</p>
                <BulletList items={rd.optional} />
              </div>
            )}
            {(rd.special_forms?.length ?? 0) > 0 && (
              <div>
                <p className="text-sm text-gray-400 mb-1.5">Особые формы</p>
                <BulletList items={rd.special_forms} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Urgency footer */}
      <div className="border-t border-gray-100 pt-5 flex items-center gap-3">
        <span className={`text-sm px-3 py-1 ${URGENCY_BADGE[s.urgency] ?? "bg-gray-100 text-gray-600"}`}>
          {URGENCY_LABEL[s.urgency] ?? s.urgency}
        </span>
        {s.days_left != null && (
          <span className="text-sm text-gray-500">{s.days_left} дней до дедлайна</span>
        )}
      </div>
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

function RunMetrics({ run }: { run: ExperimentRun | SummaryExperimentResult }) {
  return (
    <div className="flex items-center gap-3 flex-wrap text-xs text-gray-400 mb-3">
      <span>{run.input_tokens.toLocaleString("ru")} вх. токенов</span>
      <span>${run.cost_usd.toFixed(4)}</span>
      <span>{(run.duration_ms / 1000).toFixed(1)}с</span>
      {run.was_truncated && (
        <span className="text-amber-500">{run.truncated_reason}</span>
      )}
    </div>
  )
}

function RunCard({ run, accent }: { run: ExperimentRun; accent?: boolean }) {
  return (
    <div className={`border ${accent ? "border-violet-200" : "border-gray-200"} rounded-lg p-4 overflow-auto min-w-[350px]`}>
      <div className="mb-2">
        <p className={`text-sm font-medium ${accent ? "text-violet-600" : "text-gray-500"}`}>
          [{run.variant_label}] {run.variant_name}
        </p>
        <p className="text-xs text-gray-400">
          {run.strategy} · {run.model}{run.actual_model && run.actual_model !== run.model ? ` (${run.actual_model})` : ""}
        </p>
      </div>
      <RunMetrics run={run} />
      <SummaryBlock s={run.result} />
    </div>
  )
}

function ExperimentComparisonView({ runs, experimentName }: { runs: ExperimentRun[]; experimentName?: string }) {
  const [mobileIdx, setMobileIdx] = useState(0)

  if (runs.length === 0) return null

  return (
    <div className="mt-4 border-t border-gray-100 pt-4">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs font-medium text-violet-600 bg-violet-50 px-2 py-0.5 rounded">A/B тест</span>
        {experimentName && <span className="text-xs text-gray-400">{experimentName}</span>}
      </div>

      {/* Desktop */}
      {runs.length <= 2 ? (
        <div className="hidden md:grid grid-cols-2 gap-4">
          {runs.map((run, i) => (
            <RunCard key={run.id} run={run} accent={i > 0} />
          ))}
        </div>
      ) : (
        <div className="hidden md:flex gap-4 overflow-x-auto pb-2">
          {runs.map((run, i) => (
            <RunCard key={run.id} run={run} accent={i > 0} />
          ))}
        </div>
      )}

      {/* Mobile: tabs */}
      <div className="md:hidden">
        <div className="flex gap-2 mb-3">
          {runs.map((run, i) => (
            <button
              key={run.id}
              onClick={() => setMobileIdx(i)}
              className={`flex-1 h-8 text-sm rounded-md transition-colors ${
                mobileIdx === i
                  ? i === 0 ? "bg-gray-100 text-[#111827] font-medium" : "bg-violet-50 text-violet-700 font-medium"
                  : "text-gray-400"
              }`}
            >
              [{run.variant_label}]
            </button>
          ))}
        </div>
        {runs[mobileIdx] && (
          <>
            <p className="text-sm font-medium text-gray-500 mb-1">{runs[mobileIdx].variant_name}</p>
            <p className="text-xs text-gray-400 mb-2">{runs[mobileIdx].strategy} · {runs[mobileIdx].model}{runs[mobileIdx].actual_model && runs[mobileIdx].actual_model !== runs[mobileIdx].model ? ` (${runs[mobileIdx].actual_model})` : ""}</p>
            <RunMetrics run={runs[mobileIdx]} />
            <SummaryBlock s={runs[mobileIdx].result} />
          </>
        )}
      </div>
    </div>
  )
}

function LegacyComparisonView({ ragExp, fullExp }: { ragExp: SummaryExperimentResult; fullExp: SummaryExperimentResult }) {
  const runs: ExperimentRun[] = [ragExp, fullExp].map((exp, i) => ({
    ...exp,
    variant_label: i === 0 ? "A" : "B",
    variant_name: i === 0 ? "RAG" : "Full",
    strategy: exp.strategy,
    model: exp.model,
  }))
  return <ExperimentComparisonView runs={runs} experimentName="RAG vs Full" />
}

function AiSummaryBlock({ tenderId, initialSummary }: { tenderId: number; initialSummary: TenderSummary | null }) {
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState<TenderSummary | null>(initialSummary)
  const [phase, setPhase] = useState<SummaryPhase>("idle")
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const downloadStartRef = useRef<number | null>(null)

  const { data: docs = [] } = useDocsQuery(tenderId, downloading)

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => profileApi.getMe(),
    staleTime: 5 * 60 * 1000,
  })
  const isStaff = (me as Record<string, unknown>)?.is_staff === true

  const { data: legacyExperiments = [] } = useQuery({
    queryKey: ["experiments", tenderId],
    queryFn: () => tendersApi.getExperiments(tenderId),
    enabled: isStaff,
    staleTime: 30_000,
  })

  const { data: namedExperiments = [] } = useQuery({
    queryKey: ["named-experiments", tenderId],
    queryFn: () => experimentsApi.listForTender(tenderId),
    enabled: isStaff,
    staleTime: 30_000,
  })

  const [selectedExpId, setSelectedExpId] = useState<number | null>(null)
  const activeExpId = selectedExpId ?? (namedExperiments.length > 0 ? namedExperiments[0].id : null)

  const { data: expRuns = [] } = useQuery({
    queryKey: ["experiment-runs", activeExpId, tenderId],
    queryFn: () => experimentsApi.getRuns(activeExpId!, tenderId),
    enabled: isStaff && activeExpId !== null,
    staleTime: 30_000,
  })

  const [expError] = useState<string | null>(null)

  const latestRag = legacyExperiments.find((e) => e.strategy === "rag")
  const latestFull = legacyExperiments.find((e) => e.strategy === "full")
  const canCompareLegacy = !!latestRag && !!latestFull && namedExperiments.length === 0

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
    const elapsed = downloadStartRef.current ? Date.now() - downloadStartRef.current : 0
    if (docsAreReady(docs) || (elapsed > 30_000 && docs.length === 0)) {
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
      downloadStartRef.current = Date.now()
      const timeoutId = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["tender-docs", tenderId] })
      }, 32_000)
      try {
        await tendersApi.downloadDocs(tenderId)
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ["tender-docs", tenderId] })
        }, 1500)
      } catch {
        clearTimeout(timeoutId)
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
        <div className="ml-auto flex items-center gap-3">
          {summary && phase === "idle" && (
            <button
              onClick={() => handleGenerate(true)}
              className="text-sm text-gray-400 hover:text-[#111827] transition-colors"
            >
              обновить
            </button>
          )}
        </div>
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

        {expError && (
          <p className="mt-3 text-sm text-red-500">{expError}</p>
        )}

        {isStaff && namedExperiments.length > 0 && (
          <div className="mt-4 border-t border-gray-100 pt-4">
            {namedExperiments.length > 1 && (
              <div className="flex items-center gap-2 mb-3 overflow-x-auto">
                {namedExperiments.map((exp) => (
                  <button
                    key={exp.id}
                    onClick={() => setSelectedExpId(exp.id)}
                    className={`shrink-0 text-xs px-3 py-1 rounded-md transition-colors ${
                      activeExpId === exp.id
                        ? "bg-violet-100 text-violet-700 font-medium"
                        : "text-gray-400 hover:text-gray-600"
                    }`}
                  >
                    {exp.name}
                  </button>
                ))}
              </div>
            )}
            {expRuns.length > 0 && (
              <ExperimentComparisonView
                runs={expRuns}
                experimentName={namedExperiments.find((e) => e.id === activeExpId)?.name}
              />
            )}
          </div>
        )}

        {canCompareLegacy && (
          <LegacyComparisonView ragExp={latestRag!} fullExp={latestFull!} />
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

function renderMarkdown(text: string) {
  const lines = text.split("\n")
  const elements: React.ReactNode[] = []
  let listItems: React.ReactNode[] = []
  let listType: "ul" | "ol" | null = null

  function flushList() {
    if (listItems.length > 0 && listType) {
      const Tag = listType
      elements.push(<Tag key={`list-${elements.length}`} className={listType === "ol" ? "list-decimal pl-5 my-1 space-y-0.5" : "list-disc pl-5 my-1 space-y-0.5"}>{listItems}</Tag>)
      listItems = []
      listType = null
    }
  }

  function inlineFmt(s: string): React.ReactNode[] {
    const parts: React.ReactNode[] = []
    const re = /\*\*(.+?)\*\*/g
    let last = 0
    let m: RegExpExecArray | null
    while ((m = re.exec(s)) !== null) {
      if (m.index > last) parts.push(s.slice(last, m.index))
      parts.push(<strong key={m.index}>{m[1]}</strong>)
      last = re.lastIndex
    }
    if (last < s.length) parts.push(s.slice(last))
    return parts
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const olMatch = line.match(/^\d+\.\s+(.*)/)
    const ulMatch = line.match(/^[-·•]\s+(.*)/)

    if (olMatch) {
      if (listType !== "ol") flushList()
      listType = "ol"
      listItems.push(<li key={i}>{inlineFmt(olMatch[1])}</li>)
    } else if (ulMatch) {
      if (listType !== "ul") flushList()
      listType = "ul"
      listItems.push(<li key={i}>{inlineFmt(ulMatch[1])}</li>)
    } else {
      flushList()
      if (line.trim() === "") {
        elements.push(<br key={i} />)
      } else {
        elements.push(<p key={i} className="my-0.5">{inlineFmt(line)}</p>)
      }
    }
  }
  flushList()
  return <>{elements}</>
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
                          <div className="text-[15px] text-gray-700 leading-relaxed">{renderMarkdown(msg.text)}</div>
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

function TenderDetailPageInner() {
  const router = useRouter()
  const { id } = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const profileIdParam = searchParams.get("profile_id")
  const profileId = profileIdParam ? Number(profileIdParam) : null
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
    try {
      const parsed = JSON.parse(tender.ai_summary)
      if (parsed.version !== 2) return null
      return parsed
    } catch { return null }
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
              {tender.source === "bidzaar" && (
                <span className="text-sm px-3 py-1 bg-amber-50 text-amber-700 border border-amber-200 font-medium">
                  Bidzaar B2B
                </span>
              )}
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
          <PipelineStatusButtons tenderId={tender.id} profileId={profileId} />

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
          {tender.source !== "bidzaar" && <DocumentsBlock tenderId={tender.id} />}

          {/* AI summary */}
          {tender.source !== "bidzaar" && <AiSummaryBlock tenderId={tender.id} initialSummary={initialSummary} />}

          {/* Chat */}
          {tender.source !== "bidzaar" ? (
            <TenderChat tenderId={tender.id} />
          ) : (
            <div className="mb-8 p-5 border border-amber-200 bg-amber-50 rounded-xl">
              <p className="text-sm font-medium text-amber-800 mb-1">Документы и RAG-чат недоступны</p>
              <p className="text-sm text-amber-700">
                Это коммерческий тендер с площадки Bidzaar. Документы закупки доступны напрямую на платформе.
              </p>
            </div>
          )}

          {/* Source link */}
          <a
            href={tender.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2.5 h-11 px-5 text-base font-medium border border-gray-200 text-gray-700 hover:text-[#111827] hover:border-gray-300 transition-colors"
          >
            <ExternalLink className="w-5 h-5" />
            {tender.source === "bidzaar" ? "Открыть на Bidzaar" : "Открыть на ЕИС"}
          </a>
        </div>
      </div>
    </div>
  )
}

export default function TenderDetailPage() {
  return (
    <Suspense>
      <TenderDetailPageInner />
    </Suspense>
  )
}
