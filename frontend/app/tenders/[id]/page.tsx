"use client"

import { useEffect, useRef, useState, Suspense } from "react"
import { useRouter, useParams, useSearchParams } from "next/navigation"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { client, tendersApi, profileApi, experimentsApi, type Tender, type TenderSummary, type TenderSummaryV2, type AnySummary, isV2Summary, type TenderDoc, type SummaryExperimentResult, type ExperimentRun } from "@/lib/api"
import { AlertTriangle, Building2, Calendar, Check, ChevronDown, ChevronLeft, ClipboardList, Clock, Copy, DollarSign, Download, ExternalLink, FileText, Loader2, Minus, RefreshCw, Send, Shield, Sparkles, XCircle, Wrench } from "lucide-react"
import Link from "next/link"
import { PipelineStatusButtons } from "@/components/pipeline-status-buttons"
import { TenderCard } from "@/components/tender-card"

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
  other: "Иной способ",
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

function fmtVolume(n: number | string): string {
  const num = typeof n === "string" ? parseFloat(n) : n
  return num.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + "\u00A0₽"
}

function SectionHeader({ icon: Icon, title }: { icon: React.ElementType; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-4 h-4 text-gray-400" />
      <span className="text-xs font-medium text-gray-400 uppercase tracking-wider">{title}</span>
    </div>
  )
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return <h4 className="text-sm font-semibold uppercase tracking-wide text-gray-700 mb-2 mt-6 first:mt-0">{children}</h4>
}

function FieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (!value) return null
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="text-xs font-medium uppercase text-gray-500 shrink-0">{label}:</span>
      <span className="text-gray-900 break-words min-w-0">{value}</span>
    </div>
  )
}

function WarningBlock({ children, variant = "amber" }: { children: React.ReactNode; variant?: "amber" | "green" | "red" }) {
  const styles = {
    amber: "border-amber-500 bg-amber-50",
    green: "border-emerald-500 bg-emerald-50",
    red: "border-red-500 bg-red-50",
  }
  return (
    <div className={`border-l-4 p-3 mt-4 ${styles[variant]}`}>
      <p className="text-sm text-gray-900 leading-relaxed">{children}</p>
    </div>
  )
}

function BulletList({ items, className = "text-gray-800" }: { items: string[]; className?: string }) {
  if (!items.length) return null
  return (
    <ul className="space-y-1.5">
      {items.map((item, i) => (
        <li key={i} className={`flex items-start gap-2.5 text-sm leading-relaxed ${className}`}>
          <span className="text-gray-400 mt-1 shrink-0 text-[8px]">●</span>
          {item}
        </li>
      ))}
    </ul>
  )
}

function SummaryBlock({ s }: { s: TenderSummary }) {
  const ca = s.customer_analysis ?? { name: "", inn: "", region: "", okved_main: "", tender_count: 0, total_volume: 0, notes: [] }
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

const SEVERITY_BADGE: Record<string, string> = {
  high: "bg-red-50 text-red-700 border-red-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-gray-50 text-gray-600 border-gray-200",
}

const RISK_BADGE: Record<string, string> = {
  high: "bg-red-50 text-red-700 border-red-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-gray-100 text-gray-600 border-gray-200",
}

const RELIABILITY_BADGE: Record<string, string> = {
  high: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low: "bg-red-50 text-red-700 border-red-200",
}

const RELIABILITY_LABEL: Record<string, string> = {
  high: "Высокая",
  medium: "Средняя",
  low: "Низкая",
}

const RISK_BORDER: Record<string, string> = {
  high: "border-l-red-500",
  medium: "border-l-amber-500",
  low: "border-l-gray-300",
}

function RiskItem({ risk, severity }: { risk: string; severity: string }) {
  return (
    <div className={`border-l-4 pl-3 py-1.5 flex items-start justify-between gap-3 ${RISK_BORDER[severity] ?? "border-l-gray-300"}`}>
      <span className="text-sm font-medium text-gray-900 leading-relaxed">{risk}</span>
      {severity && (
        <span className={`text-[11px] px-1.5 py-0.5 border shrink-0 ${SEVERITY_BADGE[severity] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
          {severity}
        </span>
      )}
    </div>
  )
}

function Disclosure({ title, icon: Icon, defaultOpen = false, count, children }: {
  title: string
  icon: React.ElementType
  defaultOpen?: boolean
  count?: number | null
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-t border-gray-200">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between py-4">
        <div className="flex items-center gap-2.5">
          <Icon className="w-[18px] h-[18px] text-gray-700" />
          <span className="text-lg font-semibold text-gray-900">{title}</span>
          {count != null && count > 0 && <span className="text-sm text-gray-500">({count})</span>}
        </div>
        <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>
      <div className={`grid transition-all duration-200 ${open ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
        <div className="overflow-hidden">
          <div className="pb-6">{children}</div>
        </div>
      </div>
    </div>
  )
}

function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null
  const diff = new Date(dateStr).getTime() - Date.now()
  return Math.ceil(diff / (1000 * 60 * 60 * 24))
}

function DeadlineCountdown({ deadline }: { deadline: string | null }) {
  const days = daysUntil(deadline)
  if (days == null) return <span className="text-gray-400">—</span>
  if (days < 0) return <span className="text-red-600 font-medium">Истёк</span>
  if (days === 0) return <span className="text-red-600 font-medium">Сегодня</span>
  if (days <= 3) return <span className="text-red-600 font-medium">{days} дн.</span>
  if (days <= 7) return <span className="text-amber-600 font-medium">{days} дн.</span>
  return <span className="text-gray-700 font-medium">{days} дн.</span>
}

const GENERATION_STEPS = [
  { id: 1, name: "Анализ заказчика", duration: 5 },
  { id: 2, name: "Описание работ", duration: 7 },
  { id: 3, name: "Условия оплаты", duration: 5 },
  { id: 4, name: "Сроки и этапы", duration: 5 },
  { id: 5, name: "Требования к участнику", duration: 7 },
  { id: 6, name: "Анализ рисков", duration: 8 },
]

const TOTAL_DURATION = GENERATION_STEPS.reduce((s, st) => s + st.duration, 0)

function GenerationProgress() {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(prev => prev + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  let cumulative = 0
  let currentIdx = 0
  for (let i = 0; i < GENERATION_STEPS.length; i++) {
    cumulative += GENERATION_STEPS[i].duration
    if (elapsed < cumulative) { currentIdx = i; break }
    if (i === GENERATION_STEPS.length - 1) currentIdx = i
  }

  const step = GENERATION_STEPS[currentIdx]
  const isStuck = elapsed >= TOTAL_DURATION
  const label = isStuck ? "Финализация" : step.name
  const pct = isStuck ? 95 : Math.min(Math.round((elapsed / TOTAL_DURATION) * 95), 95)
  const remaining = isStuck ? 3 : Math.max(3, (GENERATION_STEPS.length - step.id) * 5)

  return (
    <div>
      <p className="text-base font-medium text-gray-900 mb-3">{label}...</p>

      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-gray-900 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="text-sm text-gray-500 tabular-nums min-w-[3ch]">{pct}%</span>
      </div>

      <p className="text-sm text-gray-500">
        Шаг {step.id} из {GENERATION_STEPS.length} · ~{remaining} секунд осталось
      </p>
    </div>
  )
}

function RiskGroup({ title, risks }: { title: string; risks: { risk: string; severity: string }[] }) {
  if (!risks?.length) return null
  return (
    <div>
      <SubHeading>{title} ({risks.length})</SubHeading>
      <div className="space-y-2">{risks.map((r, i) => <RiskItem key={i} {...r} />)}</div>
    </div>
  )
}

function SummaryV2Sections({ s, tender }: { s: TenderSummaryV2; tender: Tender }) {
  const risks = s.risks
  const cust = s.customer_analysis
  const work = s.work_description
  const fin = s.financial
  const tl = s.timeline
  const req = s.requirements

  const totalRisks = (risks?.certification_risks?.length ?? 0) + (risks?.financial_risks?.length ?? 0) +
    (risks?.technical_risks?.length ?? 0) + (risks?.legal_risks?.length ?? 0) +
    (risks?.timeline_risks?.length ?? 0) + (risks?.unusual_conditions?.length ?? 0)

  return (
    <div>
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b border-gray-200 px-6 py-3">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          {tender.law_type && (
            <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 border border-gray-200">{tender.law_type}</span>
          )}
          <span className="text-sm font-medium text-gray-900 truncate">{tender.title}</span>
        </div>
        <div className="flex items-center gap-4 flex-wrap text-sm">
          <span className="font-semibold text-gray-900">{fmt(tender.nmck)}</span>
          <span className="flex items-center gap-1 text-gray-500">
            <Clock className="w-3.5 h-3.5" />
            <DeadlineCountdown deadline={tender.deadline_at} />
          </span>
          {risks?.overall_risk && (
            <span className={`text-xs px-2 py-0.5 border ${RISK_BADGE[risks.overall_risk] ?? "bg-gray-100 text-gray-600 border-gray-200"}`}>
              Риск: {risks.overall_risk}
            </span>
          )}
          {cust?.reliability && (
            <span className={`text-xs px-2 py-0.5 border ${RELIABILITY_BADGE[cust.reliability] ?? "bg-gray-100 text-gray-600 border-gray-200"}`}>
              {RELIABILITY_LABEL[cust.reliability] ?? cust.reliability}
            </span>
          )}
        </div>
      </div>

      <div className="px-6">
        {/* 1. Customer (КТО) */}
        {cust && (
          <Disclosure title="Заказчик" icon={Building2} defaultOpen={true} count={null}>
            <div className="space-y-3">
              <div className="flex items-center gap-3 flex-wrap text-[15px]">
                <span className="text-gray-900 font-medium">{cust.name || "Не указан"}</span>
                {cust.inn && <span className="text-gray-400 font-mono text-sm">ИНН {cust.inn}</span>}
              </div>
              <div className="space-y-1">
                <FieldRow label="Регион" value={cust.region} />
                <FieldRow label="Тип" value={cust.org_type} />
                <FieldRow label="Отрасль" value={cust.industry} />
                <FieldRow label="ОКВЭД" value={cust.okved_main} />
                <FieldRow label="Основана" value={cust.founded_date} />
                <FieldRow label="Статус" value={cust.status} />
                <FieldRow label="Руководитель" value={cust.director_name} />
              </div>
              {cust.financials?.revenue_rub != null && (
                <>
                  <SubHeading>Финансы</SubHeading>
                  <div className="space-y-1">
                    <FieldRow label="Выручка" value={fmtVolume(cust.financials.revenue_rub)} />
                    <FieldRow label="Прибыль" value={cust.financials.profit_rub != null ? fmtVolume(cust.financials.profit_rub) : null} />
                    <FieldRow label="Сотрудники" value={cust.financials.employees_count} />
                  </div>
                </>
              )}
              {cust.procurement_history?.total_purchases != null && cust.procurement_history.total_purchases > 0 && (
                <>
                  <SubHeading>Закупочная история</SubHeading>
                  <div className="space-y-1">
                    <FieldRow label="Как заказчик" value={`${cust.procurement_history.total_purchases} закупок`} />
                    <FieldRow label="Сумма закупок" value={cust.procurement_history.total_amount_rub != null ? fmtVolume(cust.procurement_history.total_amount_rub) : null} />
                    <FieldRow label="Как поставщик" value={cust.procurement_history.as_supplier_count != null ? `${cust.procurement_history.as_supplier_count} закупок` : null} />
                  </div>
                </>
              )}
              {(cust.risk_indicators?.arbitration_count || cust.risk_indicators?.fssp_count || cust.risk_indicators?.licenses_count) && (
                <>
                  <SubHeading>Индикаторы</SubHeading>
                  <div className="space-y-1">
                    <FieldRow label="Арбитражные дела" value={cust.risk_indicators.arbitration_count != null ? cust.risk_indicators.arbitration_count : null} />
                    <FieldRow label="Исп. производства ФССП" value={cust.risk_indicators.fssp_count != null ? cust.risk_indicators.fssp_count : null} />
                    <FieldRow label="Лицензий" value={cust.risk_indicators.licenses_count != null ? cust.risk_indicators.licenses_count : null} />
                    <FieldRow label="Лицензии" value={cust.risk_indicators.licenses_summary || null} />
                  </div>
                </>
              )}
              {(cust.risk_indicators?.red_flags?.length ?? 0) > 0 && (
                <BulletList items={cust.risk_indicators.red_flags.filter((f: string) => !/^[a-z_][a-z_0-9]*\s*[:=]\s*(true|false|null|\d+)$/i.test(f))} className="text-amber-600" />
              )}
              {cust.reliability && (
                <div className="flex items-center gap-2 mt-2">
                  <span className="text-xs font-medium uppercase text-gray-500">Надёжность:</span>
                  <span className={`text-xs px-2 py-0.5 border ${RELIABILITY_BADGE[cust.reliability] ?? "bg-gray-100 text-gray-600 border-gray-200"}`}>
                    {RELIABILITY_LABEL[cust.reliability] ?? cust.reliability}
                  </span>
                </div>
              )}
              {(cust.notes?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Заметки</SubHeading>
                  <BulletList items={cust.notes} />
                </>
              )}
            </div>
          </Disclosure>
        )}

        {/* 2. Work (ЧТО) */}
        {work && (
          <Disclosure title="Описание работ" icon={Wrench} defaultOpen={true} count={work.scope?.main_activities?.length}>
            <div className="space-y-3">
              {work.tender_type && (
                <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 border border-gray-200">{work.tender_type}</span>
              )}
              <p className="text-sm leading-relaxed text-gray-900">{work.subject}</p>

              {(work.scope?.main_activities?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Основные работы</SubHeading>
                  <BulletList items={work.scope.main_activities} />
                </>
              )}
              {(work.scope?.volume_metrics?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Объёмы</SubHeading>
                  <div className="space-y-1">
                    {work.scope.volume_metrics.map((m, i) => (
                      <FieldRow key={i} label={m.metric} value={m.value} />
                    ))}
                  </div>
                </>
              )}
              {(work.scope?.deliverables?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Результаты</SubHeading>
                  <BulletList items={work.scope.deliverables} />
                </>
              )}
              {work.location?.address && (
                <FieldRow label="Место" value={`${work.location.address}${work.location.region ? `, ${work.location.region}` : ""}`} />
              )}
              {work.subcontracting?.allowed != null && (
                <FieldRow label="Субподряд" value={work.subcontracting.allowed ? `да${work.subcontracting.max_pct ? ` (до ${work.subcontracting.max_pct}%)` : ""}` : "нет"} />
              )}
              {((work.technical_specs?.standards?.length ?? 0) > 0 || (work.technical_specs?.materials?.length ?? 0) > 0 || (work.technical_specs?.equipment?.length ?? 0) > 0) && (
                <>
                  <SubHeading>Технические требования</SubHeading>
                  {(work.technical_specs?.standards?.length ?? 0) > 0 && <BulletList items={work.technical_specs.standards} />}
                  {(work.technical_specs?.materials?.length ?? 0) > 0 && (
                    <>
                      <p className="text-xs font-medium text-gray-500 mt-3 mb-1">Материалы</p>
                      <BulletList items={work.technical_specs.materials} />
                    </>
                  )}
                  {(work.technical_specs?.equipment?.length ?? 0) > 0 && (
                    <>
                      <p className="text-xs font-medium text-gray-500 mt-3 mb-1">Оборудование</p>
                      <BulletList items={work.technical_specs.equipment} />
                    </>
                  )}
                </>
              )}
              {(work.acceptance?.procedure || work.acceptance?.warranty_months != null) && (
                <>
                  <SubHeading>Приёмка</SubHeading>
                  <div className="space-y-1">
                    <FieldRow label="Процедура" value={work.acceptance.procedure} />
                    <FieldRow label="Гарантия" value={work.acceptance.warranty_months != null ? `${work.acceptance.warranty_months} мес.` : null} />
                  </div>
                </>
              )}
            </div>
          </Disclosure>
        )}

        {/* 3. Financial (ЗА СКОЛЬКО) */}
        {fin && (
          <Disclosure title="Финансы" icon={DollarSign} defaultOpen={true}>
            <div className="grid md:grid-cols-2 gap-x-6 gap-y-4 items-start">
              <div className="space-y-1 min-w-0">
                <SubHeading>Оплата</SubHeading>
                {fin.advance?.has_advance ? (
                  <FieldRow label="Аванс" value={`${fin.advance.amount_pct ? `${fin.advance.amount_pct}%` : fin.advance.amount_rub ? fmtVolume(fin.advance.amount_rub) : "да"}${fin.advance.description ? ` — ${fin.advance.description}` : ""}`} />
                ) : (
                  <FieldRow label="Аванс" value="не предусмотрен" />
                )}
                {fin.payment?.structure && (
                  <FieldRow label="Оплата" value={`${fin.payment.schedule_description ?? fin.payment.structure}${fin.payment.term_days ? `, ${fin.payment.term_days} ${fin.payment.term_days_type ?? "дн."}` : ""}`} />
                )}
                {fin.funding_source && <FieldRow label="Источник" value={fin.funding_source} />}
              </div>
              <div className="space-y-1 min-w-0">
                <SubHeading>Обеспечение и штрафы</SubHeading>
                {(fin.securities?.bid_pct != null || fin.securities?.bid_amount_rub != null) && (
                  <FieldRow label="Заявка" value={`${fin.securities.bid_pct ? `${fin.securities.bid_pct}%` : ""}${fin.securities.bid_amount_rub ? ` (${fmtVolume(fin.securities.bid_amount_rub)})` : ""}`} />
                )}
                {(fin.securities?.contract_pct != null || fin.securities?.contract_amount_rub != null) && (
                  <FieldRow label="Контракт" value={`${fin.securities.contract_pct ? `${fin.securities.contract_pct}%` : ""}${fin.securities.contract_amount_rub ? ` (${fmtVolume(fin.securities.contract_amount_rub)})` : ""}`} />
                )}
                {fin.securities?.contract_form && <FieldRow label="Форма" value={fin.securities.contract_form} />}
                {fin.penalties?.delay_pen_formula && <FieldRow label="Пеня" value={fin.penalties.delay_pen_formula} />}
                {fin.penalties?.fixed_fine_rub != null && (
                  <FieldRow label="Штраф" value={`${fmtVolume(fin.penalties.fixed_fine_rub)}${fin.penalties.fixed_fine_basis ? ` (${fin.penalties.fixed_fine_basis})` : ""}`} />
                )}
              </div>
            </div>
            {fin.antidumping?.applicable && (
              <WarningBlock variant="amber">Антидемпинг: порог {fin.antidumping.threshold_pct}%, множитель {fin.antidumping.multiplier}x</WarningBlock>
            )}
            {fin.cash_flow_note && (
              <WarningBlock variant={
                fin.cash_flow_note.includes("Низк") ? "green" :
                fin.cash_flow_note.includes("Высок") ? "red" : "amber"
              }>{fin.cash_flow_note}</WarningBlock>
            )}
          </Disclosure>
        )}

        {/* 4. Timeline (КОГДА) */}
        {tl && (
          <Disclosure title="Сроки" icon={Calendar} defaultOpen={true}>
            <div className="space-y-3">
              {tl.total_duration?.description && (
                <>
                  <SubHeading>Длительность</SubHeading>
                  <p className="text-sm font-medium text-gray-900">{tl.total_duration.description}</p>
                </>
              )}
              {(tl.stages?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Этапы</SubHeading>
                  <ol className="space-y-1.5">
                    {tl.stages.map((st, i) => (
                      <li key={i} className="flex items-start gap-2.5 text-sm text-gray-700">
                        <span className="text-gray-400 shrink-0 w-5 text-right">{st.number || i + 1}.</span>
                        <div>
                          <span className="text-gray-900">{st.name}</span>
                          {st.duration_days && <span className="text-gray-400"> — {st.duration_days} дн.</span>}
                          {(st.deliverables?.length ?? 0) > 0 && (
                            <ul className="mt-1 space-y-0.5">
                              {st.deliverables.map((d, j) => (
                                <li key={j} className="text-sm text-gray-500 flex items-start gap-2">
                                  <span className="text-gray-300 mt-0.5 shrink-0">·</span>{d}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </li>
                    ))}
                  </ol>
                </>
              )}
              {(tl.key_dates?.submission_deadline || tl.key_dates?.auction_date || tl.key_dates?.warranty_months != null) && (
                <>
                  <SubHeading>Ключевые даты</SubHeading>
                  <div className="space-y-1">
                    <FieldRow label="Подача" value={tl.key_dates.submission_deadline} />
                    <FieldRow label="Аукцион" value={tl.key_dates.auction_date} />
                    <FieldRow label="Гарантия" value={tl.key_dates.warranty_months != null ? `${tl.key_dates.warranty_months} мес.` : null} />
                  </div>
                </>
              )}
              {tl.urgency_note && (
                <WarningBlock variant={
                  tl.urgency_note.includes("крит") || tl.urgency_note.includes("Крит") ? "red" :
                  tl.urgency_note.includes("сроч") || tl.urgency_note.includes("Сроч") ? "amber" : "amber"
                }>{tl.urgency_note}</WarningBlock>
              )}
            </div>
          </Disclosure>
        )}

        {/* 5. Requirements (КТО МОЖЕТ) */}
        {req && (
          <Disclosure title="Требования" icon={ClipboardList} defaultOpen={true} count={
            (req.eligibility?.licenses?.length ?? 0) + (req.submission?.documents?.length ?? 0)
          }>
            <div className="space-y-3">
              {(req.eligibility?.licenses?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Лицензии</SubHeading>
                  <BulletList items={req.eligibility.licenses.map(l => `${l.name}${l.issuer ? ` (${l.issuer})` : ""}${l.mandatory ? "" : " — желательно"}`)} />
                </>
              )}
              {req.eligibility?.sro?.required && (
                <FieldRow label="СРО" value={req.eligibility.sro.type ?? "требуется"} />
              )}
              {req.eligibility?.experience?.description && (
                <FieldRow label="Опыт" value={req.eligibility.experience.description} />
              )}
              {(req.eligibility?.staff?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Персонал</SubHeading>
                  <BulletList items={req.eligibility.staff.map(st => `${st.role}${st.count ? ` × ${st.count}` : ""}${st.qualifications ? ` — ${st.qualifications}` : ""}`)} />
                </>
              )}
              {(req.eligibility?.other?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Прочие требования</SubHeading>
                  <BulletList items={req.eligibility.other} />
                </>
              )}
              {(req.evaluation_criteria?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Критерии оценки</SubHeading>
                  <div className="space-y-3">
                    {req.evaluation_criteria.map((c, i) => (
                      <div key={i}>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm text-gray-900">{c.name}</span>
                          {c.weight_pct != null && (
                            <span className="text-sm font-medium text-gray-700 tabular-nums">{c.weight_pct}%</span>
                          )}
                        </div>
                        {c.weight_pct != null && (
                          <div className="w-full h-1 bg-gray-100 mt-1.5 rounded-full">
                            <div className="h-full bg-gray-900 rounded-full" style={{ width: `${c.weight_pct}%` }} />
                          </div>
                        )}
                        {c.description && <p className="text-xs text-gray-500 mt-1">{c.description}</p>}
                      </div>
                    ))}
                  </div>
                </>
              )}
              {(req.submission?.documents?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Документы для подачи</SubHeading>
                  <BulletList items={req.submission.documents.map(d => `${d.name}${d.mandatory ? "" : " (опционально)"}`)} />
                </>
              )}
              {(req.restrictions?.smp_only || req.restrictions?.national_regime) && (
                <>
                  <SubHeading>Ограничения</SubHeading>
                  {req.restrictions.smp_only && <WarningBlock variant="amber">Только для СМП/СОНКО</WarningBlock>}
                  {req.restrictions.national_regime && <FieldRow label="Режим" value="Национальный режим" />}
                </>
              )}
            </div>
          </Disclosure>
        )}

        {/* 6. Risks (ИТОГ) */}
        {risks && (
          <Disclosure title="Риски" icon={Shield} defaultOpen={true} count={totalRisks || null}>
            <div className="space-y-3">
              {risks.overall_risk && (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium uppercase text-gray-500">Общий уровень:</span>
                  <span className={`text-xs px-2 py-0.5 border font-medium ${RISK_BADGE[risks.overall_risk] ?? "bg-gray-100 text-gray-600 border-gray-200"}`}>
                    {risks.overall_risk}
                  </span>
                </div>
              )}
              {risks.risk_summary && (
                <p className="text-sm text-gray-700 leading-relaxed">{risks.risk_summary}</p>
              )}
              <RiskGroup title="Сертификационные" risks={risks.certification_risks} />
              <RiskGroup title="Финансовые" risks={risks.financial_risks} />
              <RiskGroup title="Технические" risks={risks.technical_risks} />
              <RiskGroup title="Юридические" risks={risks.legal_risks} />
              <RiskGroup title="Временные" risks={risks.timeline_risks} />
              {(risks.unusual_conditions?.length ?? 0) > 0 && (
                <>
                  <SubHeading>Необычные условия ({risks.unusual_conditions.length})</SubHeading>
                  <BulletList items={risks.unusual_conditions} className="text-amber-600" />
                </>
              )}
            </div>
          </Disclosure>
        )}
      </div>
    </div>
  )
}

function SummaryBlockV2({ s, tender }: { s: TenderSummaryV2; tender?: Tender }) {
  if (tender) return <SummaryV2Sections s={s} tender={tender} />
  return <SummaryV2Fallback s={s} />
}

function SummaryV2Fallback({ s }: { s: TenderSummaryV2 }) {
  const risks = s.risks
  const cust = s.customer_analysis
  return (
    <div className="space-y-3">
      {risks?.risk_summary && <p className="text-sm text-gray-600">{risks.risk_summary}</p>}
      {cust?.name && <p className="text-sm text-gray-500">Заказчик: {cust.name}</p>}
    </div>
  )
}

function SummaryBlockAny({ s, tender }: { s: AnySummary; tender?: Tender }) {
  if (isV2Summary(s)) return <SummaryBlockV2 s={s} tender={tender} />
  return <SummaryBlock s={s as TenderSummary} />
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
    if (downloading && docs.length > 0 && !isProcessing) {
      // Docs already exist and are all done/skipped — reset after short delay
      // to allow refetch to settle (handles repeated clicks)
      const t = setTimeout(() => setDownloading(false), 2000)
      return () => clearTimeout(t)
    }
  }, [downloading, docs.length, isProcessing])

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
      <SummaryBlockAny s={run.result} />
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
            <SummaryBlockAny s={runs[mobileIdx].result} />
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

function AiSummaryBlock({ tenderId, tender }: { tenderId: number; tender: Tender }) {
  const queryClient = useQueryClient()
  const [summary, setSummary] = useState<AnySummary | null>(null)
  const [phase, setPhase] = useState<SummaryPhase>("idle")
  const [error, setError] = useState<string | null>(null)
  const [downloading, setDownloading] = useState(false)
  const downloadStartRef = useRef<number | null>(null)
  const [autoStarted, setAutoStarted] = useState(false)

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

  const {
    data: cachedSummary,
    isLoading: loadingCache,
  } = useQuery({
    queryKey: ["tender-summary", tenderId],
    queryFn: () => tendersApi.getSummary(tenderId),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })

  async function generateSummary(refresh = false) {
    setPhase("analyzing")
    setError(null)
    try {
      const data = await tendersApi.getSummary(tenderId, refresh)
      setSummary(data)
      queryClient.setQueryData(["tender-summary", tenderId], data)
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

  useEffect(() => {
    if (phase !== "downloading") return
    const elapsed = downloadStartRef.current ? Date.now() - downloadStartRef.current : 0
    if (docsAreReady(docs) || (elapsed > 30_000 && docs.length === 0)) {
      setDownloading(false)
      generateSummary(true)
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

    if (noDocs && !autoStarted) {
      setAutoStarted(true)
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

    await generateSummary(refresh)
  }

  const effectiveSummary = summary ?? cachedSummary ?? null
  const isV2 = effectiveSummary && isV2Summary(effectiveSummary)

  if (isV2 && phase === "idle") {
    return (
      <div className="mb-8 border border-gray-200 bg-white">
        <div className="flex items-center gap-3 px-6 py-3 border-b border-gray-200">
          <Sparkles className="w-4 h-4 text-gray-400" />
          <p className="text-sm font-semibold text-[#111827]">AI-резюме</p>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={async () => {
                const res = await client.get(`/tenders/${tenderId}/summary/export/`, { params: { type: "pdf" }, responseType: "blob" })
                const url = URL.createObjectURL(res.data)
                const a = document.createElement("a"); a.href = url; a.download = `summary_${tenderId}.pdf`; a.click(); URL.revokeObjectURL(url)
              }}
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-md hover:bg-red-100 transition-colors"
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
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-md hover:bg-blue-100 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              DOCX
            </button>
            <span className="w-px h-4 bg-gray-200" />
            <button
              onClick={() => handleGenerate(true)}
              className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-[#111827] transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Перегенерировать
            </button>
          </div>
        </div>
        <SummaryV2Sections s={effectiveSummary as TenderSummaryV2} tender={tender} />

        {isStaff && (
          <div className="px-6 pb-5">
            {expError && <p className="text-sm text-red-500">{expError}</p>}
            {namedExperiments.length > 0 && (
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
            {canCompareLegacy && <LegacyComparisonView ragExp={latestRag!} fullExp={latestFull!} />}
          </div>
        )}
      </div>
    )
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
        {effectiveSummary && phase === "idle" ? (
          <SummaryBlock s={effectiveSummary as TenderSummary} />
        ) : phase === "downloading" ? (
          <DocsProgressInline docs={docs} downloading={downloading} tenderId={tenderId} />
        ) : phase === "analyzing" ? (
          <GenerationProgress />
        ) : loadingCache ? (
          <div className="flex items-center gap-3 text-[15px] text-gray-500">
            <Loader2 className="w-5 h-5 animate-spin" />
            Загружаем резюме...
          </div>
        ) : error === "quota_exceeded" ? (
          <div className="space-y-2">
            <p className="text-[15px] text-amber-600">Лимит AI-резюме исчерпан на этом тарифе.</p>
            <a href="/#pricing" className="text-sm text-violet-600 hover:text-violet-700 font-medium">
              Улучшить тариф →
            </a>
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

interface ChatMessage {
  role: "user" | "assistant"
  text: string
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
  const [streamingText, setStreamingText] = useState("")
  const [noDocs, setNoDocs] = useState(false)
  const [quotaExceeded, setQuotaExceeded] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, streamingText])

  async function handleSend() {
    const q = input.trim()
    if (!q || loading) return

    setInput("")
    setMessages((prev) => [...prev, { role: "user", text: q }])
    setLoading(true)
    setStreamingText("")

    const history = messages.map((m) => ({ role: m.role, text: m.text }))

    const controller = new AbortController()
    abortRef.current = controller

    try {
      const token = (await import("@/lib/auth")).getToken()
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api/v1"
      const res = await fetch(`${apiBase}/tenders/${tenderId}/chat/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message: q, history }),
        signal: controller.signal,
      })

      if (res.status === 402) {
        setQuotaExceeded(true)
        setMessages((prev) => prev.slice(0, -1))
        setLoading(false)
        return
      }

      if (!res.ok || !res.body) {
        setMessages((prev) => [...prev, { role: "assistant", text: "Ошибка при получении ответа." }])
        setLoading(false)
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let fullText = ""
      let buffer = ""

      while (true) {
        const { value, done } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.error === "no_docs") {
              setNoDocs(true)
              setMessages((prev) => prev.slice(0, -1))
              setLoading(false)
              return
            }
            if (data.chunk) {
              fullText += data.chunk
              setStreamingText(fullText)
            }
            if (data.done) {
              setMessages((prev) => [...prev, { role: "assistant", text: fullText }])
              setStreamingText("")
            }
          } catch { /* skip malformed lines */ }
        }
      }

      if (fullText && !streamingText) {
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.role === "assistant" && last.text === fullText) return prev
          return [...prev, { role: "assistant", text: fullText }]
        })
        setStreamingText("")
      }
    } catch (e: unknown) {
      if ((e as Error)?.name !== "AbortError") {
        setMessages((prev) => [...prev, { role: "assistant", text: "Ошибка при получении ответа." }])
      }
    } finally {
      setLoading(false)
      setStreamingText("")
      abortRef.current = null
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const questionCount = messages.filter((m) => m.role === "user").length

  return (
    <div className="mb-8 border border-gray-200 bg-white">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-200">
        <div className="flex items-center gap-2.5">
          <Send className="w-4 h-4 text-gray-700" />
          <span className="text-base font-semibold text-gray-900">Вопросы по тендеру</span>
        </div>
        {questionCount > 0 && (
          <span className="text-sm text-gray-500">{questionCount} вопрос{questionCount === 1 ? "" : questionCount < 5 ? "а" : "ов"}</span>
        )}
      </div>

      <div className="px-5 py-4">
        {quotaExceeded ? (
          <div className="space-y-2">
            <p className="text-sm text-gray-700">Лимит вопросов исчерпан на этом тарифе.</p>
            <a href="/#pricing" className="text-sm text-gray-900 font-medium hover:underline">
              Улучшить тариф →
            </a>
          </div>
        ) : noDocs ? (
          <p className="text-sm text-gray-500">
            Загрузите документы тендера, чтобы задавать вопросы.
          </p>
        ) : (
          <>
            {(messages.length > 0 || streamingText) && (
              <div className="mb-4 max-h-[500px] overflow-auto space-y-4">
                {messages.map((msg, i) => (
                  <div key={i}>
                    {msg.role === "user" ? (
                      <div className="flex justify-end">
                        <div className="bg-gray-100 rounded-2xl px-4 py-2.5 max-w-[70%]">
                          <p className="text-sm text-gray-900">{msg.text}</p>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-start gap-2.5 max-w-[85%]">
                        <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                        <div className="text-sm text-gray-900 leading-relaxed">{renderMarkdown(msg.text)}</div>
                      </div>
                    )}
                  </div>
                ))}
                {streamingText && (
                  <div className="flex items-start gap-2.5 max-w-[85%]">
                    <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                    <div className="text-sm text-gray-900 leading-relaxed">{renderMarkdown(streamingText)}</div>
                  </div>
                )}
                {loading && !streamingText && (
                  <div className="flex items-start gap-2.5">
                    <Sparkles className="w-4 h-4 text-gray-700 mt-0.5 shrink-0" />
                    <span className="text-sm text-gray-500">Думаю...</span>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}

            <div className="flex gap-2.5">
              <input
                type="text"
                className="flex-1 h-10 border border-gray-200 rounded-lg px-3.5 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
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
                className="h-10 w-10 flex items-center justify-center bg-gray-900 text-white rounded-full hover:bg-gray-800 transition-colors disabled:opacity-40"
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

function SimilarTendersBlock({ tenderId, profileId }: { tenderId: number; profileId?: number | null }) {
  const [limit, setLimit] = useState(3)
  const { data, isLoading } = useQuery<{ data: Tender[]; has_more: boolean }>({
    queryKey: ["similar-tenders", tenderId, limit],
    queryFn: () => client.get(`/tenders/${tenderId}/similar/`, { params: { limit } }).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  const tenders = data?.data ?? []
  const hasMore = data?.has_more ?? false

  if (isLoading) return null
  if (tenders.length === 0) return null

  return (
    <div className="mb-8 border border-gray-200 bg-white">
      <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-200">
        <Copy className="w-5 h-5 text-gray-400" />
        <p className="text-base font-semibold text-[#111827]">Похожие тендеры</p>
        <span className="text-sm text-gray-400">{tenders.length}</span>
      </div>
      <div className="px-6 py-5 space-y-3">
        {tenders.map((t) => (
          <TenderCard key={t.id} tender={t} profileId={profileId} />
        ))}
        {hasMore && (
          <button
            onClick={() => setLimit(prev => prev + 3)}
            className="text-sm text-gray-500 hover:text-[#111827] transition-colors"
          >
            Показать ещё
          </button>
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

  // v2 summary is fetched separately by AiSummaryBlock via React Query

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
            {tender.procedure_type && (
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
                value={tender.customer?.full_name || tender.customer?.name || tender.customer_name || "—"}
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
          <DocumentsBlock tenderId={tender.id} />

          {/* AI summary */}
          <AiSummaryBlock tenderId={tender.id} tender={tender} />

          {/* Chat */}
          <TenderChat tenderId={tender.id} />

          {/* Similar tenders */}
          <SimilarTendersBlock tenderId={tender.id} profileId={profileId} />

          {/* Source link */}
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

export default function TenderDetailPage() {
  return (
    <Suspense>
      <TenderDetailPageInner />
    </Suspense>
  )
}
