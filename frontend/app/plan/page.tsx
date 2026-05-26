"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { billingApi, type UserPlan } from "@/lib/api"
import { ProfilePricing } from "@/components/profile-pricing"

const PLAN_LABEL: Record<string, string> = { free: "Free", standard: "Standard", premium: "Premium" }

function UsageBar({ used, limit, label }: { used: number; limit: number; label: string }) {
  const pct = Math.min(100, Math.round((used / limit) * 100))
  const nearLimit = pct >= 80
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[15px]">
        <span className="text-gray-500">{label}</span>
        <span className={`font-medium tabular-nums ${nearLimit ? "text-amber-600" : "text-[#111827]"}`}>
          {used} / {limit}
        </span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${nearLimit ? "bg-amber-500" : "bg-[#111827]"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function CurrentPlanBlock({ plan }: { plan: UserPlan }) {
  const resetDate = new Date(plan.reset_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })
  const sub = plan.subscription

  const periodEnd = sub?.current_period_end
    ? new Date(sub.current_period_end).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
    : null

  return (
    <div className="border border-gray-200 bg-white">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center gap-3">
        <p className="text-base font-semibold text-[#111827]">Текущий тариф</p>
        <span className="text-sm px-2.5 py-0.5 font-medium bg-[#111827] text-white">
          {PLAN_LABEL[plan.plan] ?? plan.plan}
        </span>
        {sub && (
          <span className="text-xs text-gray-400">
            {sub.interval === "yearly" ? "годовой" : sub.interval === "halfyearly" ? "полугодовой" : "месячный"}
          </span>
        )}
      </div>
      <div className="px-6 py-5 space-y-4">
        <UsageBar used={plan.ai_summaries.used} limit={plan.ai_summaries.limit} label="AI-резюме" />
        <UsageBar used={plan.rag_questions.used} limit={plan.rag_questions.limit} label="Вопросы по тендеру" />
        <UsageBar used={plan.companies.used} limit={plan.companies.limit} label="Компании" />
        <p className="text-sm text-gray-500">Счётчики сбрасываются <span className="font-medium text-[#111827]">{resetDate}</span></p>

        {sub && sub.status === "active" && periodEnd && (
          <div className="pt-2 border-t border-gray-100">
            <p className="text-sm text-gray-500">
              Действует до <span className="font-medium text-[#111827]">{periodEnd}</span>
            </p>
          </div>
        )}

        {sub && sub.status === "expired" && (
          <div className="pt-2 border-t border-gray-100">
            <p className="text-sm text-gray-500">
              Подписка истекла.
            </p>
            <button
              onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}
              className="mt-2 text-sm font-medium text-[#111827] hover:underline"
            >
              Продлить подписку →
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default function PlanPage() {
  const router = useRouter()
  const qc = useQueryClient()

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get("payment") === "success") {
      billingApi.verify().then(() => {
        qc.invalidateQueries({ queryKey: ["billing"] })
      }).catch(() => {})
      params.delete("payment")
      const qs = params.toString()
      window.history.replaceState({}, "", window.location.pathname + (qs ? `?${qs}` : ""))
    }
  }, [qc])

  const { data: billingInfo } = useQuery<UserPlan>({
    queryKey: ["billing"],
    queryFn: () => billingApi.getInfo(),
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  })

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <div className="flex items-center justify-between px-8 h-16 border-b border-gray-200 bg-white">
        <h1 className="text-xl font-bold text-[#111827]">Мой тариф</h1>
      </div>
      <div className="px-8 py-8 max-w-4xl space-y-6">
        {billingInfo && <CurrentPlanBlock plan={billingInfo} />}
        {billingInfo && <ProfilePricing currentPlan={billingInfo} />}
      </div>
    </div>
  )
}
