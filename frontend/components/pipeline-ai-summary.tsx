"use client"

import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { client, tendersApi, isV2Summary, type TenderSummaryV2, type TenderDoc, type AnySummary } from "@/lib/api"
import { Sparkles, Loader2, Download, RefreshCw, AlertTriangle, ChevronDown } from "lucide-react"

type Phase = "idle" | "downloading" | "analyzing"

function docsAreReady(docs: TenderDoc[]): boolean {
  return docs.length > 0 && docs.every((d) =>
    d.parse_status !== "pending" && d.parse_status !== "processing"
  )
}

const RISK_COLORS: Record<string, string> = {
  high: "text-red-500",
  medium: "text-amber-500",
  low: "text-green-500",
}

const RISK_BG: Record<string, { bg: string; border: string; title: string }> = {
  high: { bg: "bg-red-50", border: "border-red-200", title: "text-red-700" },
  medium: { bg: "bg-amber-50", border: "border-amber-200", title: "text-amber-700" },
  low: { bg: "bg-green-50", border: "border-green-200", title: "text-green-700" },
}

const RISK_LABEL: Record<string, string> = {
  high: "Высокий риск",
  medium: "Средний риск",
  low: "Низкий риск",
}

const RELIABILITY_LABEL: Record<string, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
}

function fmtVolume(n: number | null | undefined): string | null {
  if (n == null) return null
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(1) + " млрд ₽"
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + " млн ₽"
  if (n >= 1_000) return (n / 1_000).toFixed(0) + " тыс ₽"
  return n.toLocaleString("ru-RU") + " ₽"
}

function Section({ title, children, defaultOpen = false }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-gray-100 last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full py-2 text-left"
      >
        <span className="text-sm font-semibold text-gray-500 uppercase tracking-wide">{title}</span>
        <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <div className="pb-3.5">{children}</div>}
    </div>
  )
}

function FieldRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value == null || value === "") return null
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-gray-400 shrink-0">{label}:</span>
      <span className="text-gray-700">{value}</span>
    </div>
  )
}

function BulletList({ items }: { items?: string[] }) {
  if (!items || items.length === 0) return null
  return (
    <ul className="space-y-0.5 text-sm text-gray-700">
      {items.map((item, i) => (
        <li key={i} className="flex gap-1.5">
          <span className="text-gray-300 shrink-0">·</span>
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function RiskList({ items, label }: { items?: { risk: string; severity: string }[]; label: string }) {
  if (!items || items.length === 0) return null
  return (
    <div className="mb-2">
      <p className="text-sm font-medium text-gray-500 mb-0.5">{label}</p>
      {items.map((r, i) => (
        <div key={i} className="flex items-start gap-1.5 text-sm text-gray-600 ml-1">
          <AlertTriangle className={`w-3 h-3 mt-0.5 shrink-0 ${RISK_COLORS[r.severity] || "text-gray-400"}`} />
          <span>{r.risk}</span>
        </div>
      ))}
    </div>
  )
}

function SummaryContent({ s }: { s: TenderSummaryV2 }) {
  const cust = s.customer_analysis
  const work = s.work_description
  const fin = s.financial
  const tl = s.timeline
  const req = s.requirements
  const risks = s.risks

  return (
    <div className="flex flex-col gap-1.5">
      {/* Work description */}
      {work && (
        <Section title="Описание работ" defaultOpen>
          <p className="text-sm text-gray-700 mb-2">{work.subject}</p>
          {(work.scope?.main_activities?.length ?? 0) > 0 && <BulletList items={work.scope.main_activities} />}
          {work.location?.address && <FieldRow label="Место" value={work.location.address} />}
        </Section>
      )}

      {/* Customer */}
      {cust && (
        <Section title="Заказчик">
          <div className="space-y-0.5">
            <FieldRow label="Название" value={cust.name} />
            <FieldRow label="ИНН" value={cust.inn} />
            <FieldRow label="Регион" value={cust.region} />
            <FieldRow label="Тип" value={cust.org_type} />
            {cust.financials?.revenue_rub != null && <FieldRow label="Выручка" value={fmtVolume(cust.financials.revenue_rub)} />}
            {cust.procurement_history?.total_purchases != null && (
              <FieldRow label="Закупки" value={`${cust.procurement_history.total_purchases} шт.`} />
            )}
            {cust.reliability && <FieldRow label="Надёжность" value={RELIABILITY_LABEL[cust.reliability] ?? cust.reliability} />}
          </div>
        </Section>
      )}

      {/* Financial */}
      {fin && (
        <Section title="Финансы">
          <div className="space-y-0.5">
            {fin.advance?.has_advance && (
              <FieldRow label="Аванс" value={fin.advance.amount_pct ? `${fin.advance.amount_pct}%` : "да"} />
            )}
            {fin.payment?.structure && <FieldRow label="Оплата" value={fin.payment.schedule_description ?? fin.payment.structure} />}
            {(fin.securities?.bid_pct != null || fin.securities?.bid_amount_rub != null) && (
              <FieldRow label="Обеспечение заявки" value={fin.securities.bid_pct ? `${fin.securities.bid_pct}%` : fmtVolume(fin.securities.bid_amount_rub)} />
            )}
            {(fin.securities?.contract_pct != null || fin.securities?.contract_amount_rub != null) && (
              <FieldRow label="Обеспечение контракта" value={fin.securities.contract_pct ? `${fin.securities.contract_pct}%` : fmtVolume(fin.securities.contract_amount_rub)} />
            )}
          </div>
        </Section>
      )}

      {/* Timeline */}
      {tl && (
        <Section title="Сроки">
          <div className="space-y-0.5">
            {tl.total_duration?.days && (
              <FieldRow label="Срок" value={`${tl.total_duration.days} ${tl.total_duration.day_type || "дн."}`} />
            )}
            {tl.key_dates?.submission_deadline && <FieldRow label="Подача" value={tl.key_dates.submission_deadline} />}
            {tl.key_dates?.auction_date && <FieldRow label="Аукцион" value={tl.key_dates.auction_date} />}
            {tl.urgency_note && <p className="text-xs text-amber-600 mt-1">{tl.urgency_note}</p>}
          </div>
        </Section>
      )}

      {/* Requirements */}
      {req && (
        <Section title="Требования">
          <div className="space-y-1">
            {(req.eligibility?.licenses?.length ?? 0) > 0 && (
              <BulletList items={req.eligibility.licenses.map(l => `${l.name}${l.mandatory ? " (обяз.)" : ""}`)} />
            )}
            {req.eligibility?.sro?.required && (
              <FieldRow label="СРО" value={req.eligibility.sro.type || "требуется"} />
            )}
            {req.eligibility?.experience?.description && (
              <FieldRow label="Опыт" value={req.eligibility.experience.description} />
            )}
            {(req.eligibility?.staff?.length ?? 0) > 0 && (
              <BulletList items={req.eligibility.staff.map(s => `${s.role}${s.count ? ` (${s.count})` : ""}${s.qualifications ? `: ${s.qualifications}` : ""}`)} />
            )}
          </div>
        </Section>
      )}

      {/* Risks */}
      {risks?.overall_risk && RISK_BG[risks.overall_risk] && (
        <Section title="Риски" defaultOpen>
          <div className={`${RISK_BG[risks.overall_risk].bg} border ${RISK_BG[risks.overall_risk].border} rounded-lg p-3.5`}>
            <p className={`text-sm font-semibold ${RISK_BG[risks.overall_risk].title} mb-2`}>
              {RISK_LABEL[risks.overall_risk]}
            </p>
            {risks.risk_summary && <p className="text-sm text-gray-600 mb-2">{risks.risk_summary}</p>}
            <RiskList items={risks.certification_risks} label="Сертификации" />
            <RiskList items={risks.financial_risks} label="Финансовые" />
            <RiskList items={risks.technical_risks} label="Технические" />
            <RiskList items={risks.legal_risks} label="Юридические" />
            <RiskList items={risks.timeline_risks} label="Сроки" />
            {(risks.unusual_conditions?.length ?? 0) > 0 && (
              <>
                <p className="text-sm font-medium text-gray-500 mb-0.5">Необычные условия</p>
                <BulletList items={risks.unusual_conditions} />
              </>
            )}
          </div>
        </Section>
      )}
    </div>
  )
}

export function PipelineAiSummary({ tenderId }: { tenderId: number }) {
  const qc = useQueryClient()
  const [phase, setPhase] = useState<Phase>("idle")
  const [error, setError] = useState<string | null>(null)


  const { data: docs = [] } = useQuery<TenderDoc[]>({
    queryKey: ["tender-docs", tenderId],
    queryFn: () => tendersApi.getDocs(tenderId),
  })

  const {
    data: cachedSummary,
    isLoading: loadingCache,
  } = useQuery({
    queryKey: ["tender-summary", tenderId],
    queryFn: () => tendersApi.getSummary(tenderId),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  const [localSummary, setLocalSummary] = useState<AnySummary | null>(null)
  const effectiveSummary = localSummary ?? cachedSummary ?? null
  const isV2 = effectiveSummary && isV2Summary(effectiveSummary)

  async function generateSummary(refresh = false) {
    setPhase("analyzing")
    setError(null)
    try {
      const data = await tendersApi.getSummary(tenderId, refresh)
      setLocalSummary(data)
      qc.setQueryData(["tender-summary", tenderId], data)
      setPhase("idle")
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 402) {
        setError("quota_exceeded")
      } else {
        setError(e instanceof Error ? e.message : "Ошибка генерации")
      }
      setPhase("idle")
    }
  }

  async function handleGenerate(refresh = false) {
    setError(null)
    if (refresh) setLocalSummary(null)
    await generateSummary(refresh)
  }

  if (isV2 && phase === "idle") {
    return (
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-gray-400" />
            <span className="text-sm font-semibold text-gray-500 uppercase tracking-wide">AI-резюме</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={async () => {
                const res = await client.get(`/tenders/${tenderId}/summary/export/`, { params: { type: "pdf" }, responseType: "blob" })
                const url = URL.createObjectURL(res.data)
                const a = document.createElement("a"); a.href = url; a.download = `summary_${tenderId}.pdf`; a.click(); URL.revokeObjectURL(url)
              }}
              className="flex items-center gap-1.5 px-2.5 py-1 text-sm font-medium text-red-600 bg-red-50 border border-red-200 rounded hover:bg-red-100 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              PDF
            </button>
            <button
              onClick={async () => {
                const res = await client.get(`/tenders/${tenderId}/summary/export/`, { params: { type: "docx" }, responseType: "blob" })
                const url = URL.createObjectURL(res.data)
                const a = document.createElement("a"); a.href = url; a.download = `summary_${tenderId}.docx`; a.click(); URL.revokeObjectURL(url)
              }}
              className="flex items-center gap-1.5 px-2.5 py-1 text-sm font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded hover:bg-blue-100 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              DOCX
            </button>
            <button
              onClick={() => handleGenerate(true)}
              className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
              title="Перегенерировать"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>
        <SummaryContent s={effectiveSummary as TenderSummaryV2} />
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="w-5 h-5 text-gray-400" />
        <span className="text-sm font-semibold text-gray-500 uppercase tracking-wide">AI-резюме</span>
      </div>

      {phase === "analyzing" ? (
        <div className="flex flex-col items-center gap-3 py-6">
          <Loader2 className="w-5 h-5 text-violet-500 animate-spin" />
          <p className="text-[15px] text-gray-400">Генерация резюме...</p>
        </div>
      ) : loadingCache ? (
        <div className="flex items-center gap-2 py-6">
          <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
          <span className="text-[15px] text-gray-400">Загрузка...</span>
        </div>
      ) : error === "quota_exceeded" ? (
        <div className="py-3">
          <p className="text-[15px] text-amber-600">Лимит AI-резюме исчерпан</p>
          <a href="/#pricing" className="text-sm text-violet-600 hover:text-violet-700 font-medium">
            Улучшить тариф
          </a>
        </div>
      ) : error ? (
        <div className="py-3">
          <p className="text-[15px] text-red-500 mb-1">{error}</p>
          <button onClick={() => handleGenerate()} className="text-sm text-gray-500 hover:text-gray-700 transition-colors">
            Попробовать снова
          </button>
        </div>
      ) : !docsAreReady(docs) ? (
        <p className="text-[15px] text-gray-400 py-3">
          {docs.length === 0
            ? "Сначала загрузите документы на вкладке «Документы»"
            : "Документы обрабатываются..."}
        </p>
      ) : (
        <button
          onClick={() => handleGenerate()}
          className="flex items-center gap-2.5 w-full justify-center py-3.5 text-[15px] text-gray-500 hover:text-[#111827] bg-gray-50 hover:bg-gray-100 rounded transition-colors"
        >
          <Sparkles className="w-5 h-5" />
          Сгенерировать резюме
        </button>
      )}
    </div>
  )
}
