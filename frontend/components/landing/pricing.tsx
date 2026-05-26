"use client"

import { useState } from "react"
import { Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { billingApi } from "@/lib/api"
import { isAuthenticated } from "@/lib/auth"

type Interval = "monthly" | "halfyearly" | "yearly"

const plans = [
  {
    key: "free",
    name: "Бесплатный",
    subtitle: "Попробовать",
    monthly: 0,
    halfyearly: 0,
    yearly: 0,
    features: [
      "1 компания",
      "До 2 AI-резюме",
      "До 10 RAG-вопросов",
      "Для вас: 10 тендеров",
    ],
  },
  {
    key: "standard",
    name: "Standard",
    subtitle: "Для специалиста",
    monthly: 2990,
    halfyearly: 14950,
    yearly: 26910,
    features: [
      "1 компания",
      "До 60 AI-резюме",
      "До 120 RAG-вопросов",
      "Для вас: без ограничений",
    ],
  },
  {
    key: "premium",
    name: "Premium",
    subtitle: "Для команды",
    monthly: 6990,
    halfyearly: 34950,
    yearly: 62910,
    features: [
      "До 10 компаний",
      "До 500 AI-резюме",
      "До 1 000 RAG-вопросов",
      "Для вас: без ограничений",
    ],
  },
  {
    key: "enterprise",
    name: "Enterprise",
    subtitle: "Для крупных команд",
    monthly: -1,
    halfyearly: -1,
    yearly: -1,
    features: [
      "Условия договорные",
      "Персональный менеджер",
      "API доступ",
    ],
  },
]

const INTERVAL_MONTHS: Record<Interval, number> = {
  monthly: 1,
  halfyearly: 6,
  yearly: 12,
}

const INTERVAL_LABEL: Record<Interval, string> = {
  monthly: "мес",
  halfyearly: "полгода",
  yearly: "год",
}

function formatPrice(price: number) {
  return price.toLocaleString("ru-RU")
}

export function Pricing() {
  const [interval, setInterval] = useState<Interval>("monthly")
  const [loading, setLoading] = useState<string | null>(null)

  async function handleCheckout(planKey: string) {
    if (!isAuthenticated()) {
      window.location.href = `/login?redirect=/profile&plan=${planKey}&interval=${interval}`
      return
    }

    setLoading(planKey)
    try {
      const result = await billingApi.checkout(planKey, interval)
      window.location.href = result.confirmation_url
    } catch {
      setLoading(null)
    }
  }

  return (
    <section id="pricing" className="bg-[#F3F4F6] py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Прозрачные тарифы
          </h2>

          <div className="mt-6 inline-flex items-center gap-1 rounded-full bg-white p-1 border border-[#D1D5DB]">
            <button
              onClick={() => setInterval("monthly")}
              className={`px-4 py-2 text-sm font-medium rounded-full transition-colors ${
                interval === "monthly"
                  ? "bg-[#111827] text-white"
                  : "text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              Месяц
            </button>
            <button
              onClick={() => setInterval("halfyearly")}
              className={`px-4 py-2 text-sm font-medium rounded-full transition-colors ${
                interval === "halfyearly"
                  ? "bg-[#111827] text-white"
                  : "text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              Полгода
              <span className="ml-1 text-xs text-emerald-600 font-semibold">-1 мес</span>
            </button>
            <button
              onClick={() => setInterval("yearly")}
              className={`px-4 py-2 text-sm font-medium rounded-full transition-colors ${
                interval === "yearly"
                  ? "bg-[#111827] text-white"
                  : "text-[#6B7280] hover:text-[#111827]"
              }`}
            >
              Год
              <span className="ml-1 text-xs text-emerald-600 font-semibold">-3 мес</span>
            </button>
          </div>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {plans.map((plan) => {
            const price = plan[interval]
            const months = INTERVAL_MONTHS[interval]
            const isEnterprise = plan.key === "enterprise"
            const isFree = plan.key === "free"

            return (
              <div
                key={plan.key}
                className={`flex flex-col border-2 bg-white p-8 ${
                  "border-[#D1D5DB]"
                }`}
              >
<div className="text-center">
                  <h3 className="text-lg font-semibold text-[#111827]">{plan.name}</h3>
                  <p className="mt-1 text-sm text-[#6B7280]">{plan.subtitle}</p>
                  <div className="mt-6">
                    {isEnterprise ? (
                      <span className="text-3xl font-bold text-[#111827]">Договорная</span>
                    ) : isFree ? (
                      <span className="text-4xl font-bold text-[#111827]">Бесплатно</span>
                    ) : (
                      <>
                        <span className="text-4xl font-bold text-[#111827] tabular-nums">
                          {formatPrice(price)}
                        </span>
                        <span className="ml-1 text-[#6B7280]">
                          ₽/{INTERVAL_LABEL[interval]}
                        </span>
                        {months > 1 && (
                          <p className="mt-1 text-sm text-[#6B7280]">
                            {formatPrice(Math.round(price / months))} ₽/мес
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </div>

                <ul className="mt-8 space-y-4">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-center gap-3">
                      <Check className="h-5 w-5 flex-shrink-0 text-[#111827]" />
                      <span className="text-sm text-[#374151]">{feature}</span>
                    </li>
                  ))}
                </ul>

                <div className="mt-auto pt-8">
                  {isEnterprise ? (
                    <a
                      href="mailto:shutov.ds@phystech.edu"
                      className="flex items-center justify-center w-full rounded-none border-2 border-[#D1D5DB] bg-white text-[#374151] hover:bg-[#F3F4F6] h-12 text-base font-semibold transition-colors"
                    >
                      Связаться
                    </a>
                  ) : isFree ? (
                    <a
                      href="/login"
                      className="flex items-center justify-center w-full rounded-none border-2 border-[#D1D5DB] bg-white text-[#374151] hover:bg-[#F3F4F6] h-12 text-base font-semibold transition-colors"
                    >
                      Начать
                    </a>
                  ) : (
                    <Button
                      onClick={() => handleCheckout(plan.key)}
                      disabled={loading === plan.key}
                      className="w-full rounded-none h-12 text-base font-semibold bg-white text-[#374151] border-[#D1D5DB] hover:bg-[#F3F4F6]"
                      variant="outline"
                    >
                      {loading === plan.key ? "Перенаправление..." : "Подключить"}
                    </Button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}
