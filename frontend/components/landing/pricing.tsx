"use client"

import { useState } from "react"
import { Check } from "lucide-react"
import { Button } from "@/components/ui/button"
import { billingApi } from "@/lib/api"
import { isAuthenticated } from "@/lib/auth"
import { plans, INTERVAL_MONTHS, INTERVAL_LABEL, formatPrice, type Interval } from "@/lib/plans"

export function Pricing() {
  const [interval, setInterval] = useState<Interval>("monthly")
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleCheckout(planKey: string) {
    setError(null)

    if (!isAuthenticated()) {
      window.location.href = `/login?redirect=/plan&plan=${planKey}&interval=${interval}`
      return
    }

    setLoading(planKey)
    try {
      const result = await billingApi.checkout(planKey, interval)
      window.location.href = result.confirmation_url
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? "Ошибка оплаты. Попробуйте позже."
      setError(msg)
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
                className="flex flex-col border-2 bg-white p-8 border-[#D1D5DB]"
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
                          {formatPrice(Math.round(price / months))}
                        </span>
                        <span className="ml-1 text-[#6B7280]">₽/мес</span>
                        {months > 1 && (
                          <p className="mt-1 text-sm text-gray-400">
                            {formatPrice(price)} ₽/{INTERVAL_LABEL[interval]}
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
                      href="https://t.me/tenderoll_support"
                      target="_blank"
                      rel="noopener noreferrer"
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

        {error && (
          <p className="mt-6 text-center text-sm text-red-600">{error}</p>
        )}
      </div>
    </section>
  )
}
