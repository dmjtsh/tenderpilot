"use client"

import { useEffect, useState } from "react"
import { useRouter, useParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { tendersApi, type Tender } from "@/lib/api"
import { ChevronLeft, ExternalLink, MessageSquare, X } from "lucide-react"
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
  const [showQuestion, setShowQuestion] = useState(false)
  const [question, setQuestion] = useState("")

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  const { data: tender, isLoading } = useQuery<Tender>({
    queryKey: ["tender", id],
    queryFn: () => tendersApi.get(Number(id)),
    enabled: !!id,
  })

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

          {/* AI summary */}
          <div className="mb-8">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">AI-резюме</p>
            {tender.ai_summary ? (
              <p className="text-sm leading-relaxed text-foreground/80">{tender.ai_summary}</p>
            ) : (
              <p className="text-sm text-muted-foreground/60 italic">
                Резюме появится после анализа документов
              </p>
            )}
          </div>

          {/* Question */}
          <div className="mb-8">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">Задать вопрос</p>
            {!showQuestion ? (
              <button
                onClick={() => setShowQuestion(true)}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                <MessageSquare className="w-4 h-4" />
                Спросить по тендеру...
              </button>
            ) : (
              <div className="space-y-2">
                <textarea
                  className="w-full h-20 bg-secondary border border-border rounded-md px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring resize-none"
                  placeholder="Какие лицензии требуются? Каков порядок подачи заявки?"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  autoFocus
                />
                <div className="flex gap-2">
                  <button
                    onClick={() => alert("RAG — в разработке")}
                    disabled={!question.trim()}
                    className="h-7 px-3 text-xs rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40"
                  >
                    Отправить
                  </button>
                  <button
                    onClick={() => { setShowQuestion(false); setQuestion("") }}
                    className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </div>

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
