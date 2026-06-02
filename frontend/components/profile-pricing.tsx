"use client"

import { useState } from "react"
import { Check } from "lucide-react"
import { billingApi, type UserPlan } from "@/lib/api"
import { plans, INTERVAL_MONTHS, INTERVAL_LABEL, formatPrice, type Interval } from "@/lib/plans"
import { trackGoal } from "@/lib/analytics"

const PAID_PLANS = plans.filter((p) => p.key === "standard" || p.key === "premium")

export function ProfilePricing({ currentPlan }: { currentPlan: UserPlan }) {
  const [interval, setInterval] = useState<Interval>("monthly")
  const [loading, setLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleCheckout(planKey: string) {
    setError(null)
    setLoading(planKey)
    try {
      const result = await billingApi.checkout(planKey, interval)
      trackGoal("checkout_started")
      window.location.href = result.confirmation_url
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? "Ошибка оплаты. Попробуйте позже."
      setError(msg)
      setLoading(null)
    }
  }

  const isCurrent = (planKey: string) =>
    currentPlan.plan === planKey && currentPlan.plan !== "free"

  return (
    <div id="pricing" className="border border-gray-200 bg-white">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <p className="text-base font-semibold text-[#111827]">Тарифы</p>
        <div className="inline-flex items-center gap-1 rounded-full bg-white p-1 border border-[#D1D5DB]">
          <button
            onClick={() => setInterval("monthly")}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              interval === "monthly"
                ? "bg-[#111827] text-white"
                : "text-[#6B7280] hover:text-[#111827]"
            }`}
          >
            Месяц
          </button>
          <button
            onClick={() => setInterval("halfyearly")}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              interval === "halfyearly"
                ? "bg-[#111827] text-white"
                : "text-[#6B7280] hover:text-[#111827]"
            }`}
          >
            Полгода
            <span className="ml-1 text-[10px] text-emerald-600 font-semibold">-1 мес</span>
          </button>
          <button
            onClick={() => setInterval("yearly")}
            className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
              interval === "yearly"
                ? "bg-[#111827] text-white"
                : "text-[#6B7280] hover:text-[#111827]"
            }`}
          >
            Год
            <span className="ml-1 text-[10px] text-emerald-600 font-semibold">-3 мес</span>
          </button>
        </div>
      </div>

      <div className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
        {PAID_PLANS.map((plan) => {
          const price = plan[interval]
          const months = INTERVAL_MONTHS[interval]
          const current = isCurrent(plan.key)

          return (
            <div
              key={plan.key}
              className={`flex flex-col p-6 border-2 ${
                current ? "border-[#111827]" : "border-[#D1D5DB]"
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-[#111827]">{plan.name}</h3>
                  <p className="text-sm text-[#6B7280]">{plan.subtitle}</p>
                </div>
                {current && (
                  <span className="text-xs px-2.5 py-1 bg-[#111827] text-white font-medium">
                    Текущий тариф
                  </span>
                )}
              </div>

              <div className="mt-4">
                <span className="text-3xl font-bold text-[#111827] tabular-nums">
                  {formatPrice(Math.round(price / months))}
                </span>
                <span className="ml-1 text-[#6B7280]">₽/мес</span>
                {months > 1 && (
                  <p className="mt-0.5 text-sm text-gray-400">
                    {formatPrice(price)} ₽/{INTERVAL_LABEL[interval]}
                  </p>
                )}
              </div>

              <ul className="mt-4 space-y-2">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2">
                    <Check className="h-4 w-4 flex-shrink-0 text-[#111827]" />
                    <span className="text-sm text-[#374151]">{feature}</span>
                  </li>
                ))}
              </ul>

              <div className="mt-auto pt-5">
                {current ? (
                  <div className="h-10 flex items-center justify-center text-sm text-[#111827] font-medium">
                    Активен
                  </div>
                ) : (
                  <button
                    onClick={() => handleCheckout(plan.key)}
                    disabled={loading === plan.key}
                    className="w-full h-10 text-sm font-semibold border-2 border-[#D1D5DB] text-[#374151] hover:bg-[#F3F4F6] transition-colors disabled:opacity-50"
                  >
                    {loading === plan.key
                      ? "Перенаправление..."
                      : currentPlan.plan !== "free"
                        ? "Сменить тариф"
                        : "Подключить"}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {error && (
        <div className="px-6 pb-4">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}
    </div>
  )
}
