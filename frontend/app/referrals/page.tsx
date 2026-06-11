"use client"

import { useEffect, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Copy, Check, Users, BadgeCheck } from "lucide-react"
import { referralsApi, type ReferralInvited } from "@/lib/api"
import { isAuthenticated } from "@/lib/auth"
import { useRouter } from "next/navigation"

function maskEmail(email: string): string {
  const [local, domain] = email.split("@")
  if (!domain) return email
  const masked = local.length > 2 ? local[0] + "***" + local[local.length - 1] : local[0] + "***"
  return `${masked}@${domain}`
}

function StatusBadge({ status }: { status: ReferralInvited["status"] }) {
  if (status === "converted") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
        <BadgeCheck className="w-3 h-3" />
        Оплатил
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200">
      <Users className="w-3 h-3" />
      Зарегистрировался
    </span>
  )
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-8 bg-gray-100 rounded w-48" />
      <div className="h-24 bg-gray-100 rounded" />
      <div className="flex gap-4">
        <div className="h-20 bg-gray-100 rounded flex-1" />
        <div className="h-20 bg-gray-100 rounded flex-1" />
      </div>
      <div className="h-40 bg-gray-100 rounded" />
    </div>
  )
}

export default function ReferralsPage() {
  const router = useRouter()
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login")
    }
  }, [router])

  const { data, isPending, isFetching } = useQuery({
    queryKey: ["referrals", "me"],
    queryFn: referralsApi.getMe,
    enabled: isAuthenticated(),
  })

  function handleCopy() {
    if (!data?.link) return
    navigator.clipboard.writeText(data.link).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  if (isPending && isFetching) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10">
        <Skeleton />
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-10">
      <h1 className="text-2xl font-bold text-[#111827] mb-8">Реферальная программа</h1>

      {/* Referral link block */}
      <div className="border border-gray-200 rounded-lg p-5 mb-6 bg-white">
        <p className="text-sm font-medium text-gray-700 mb-3">Ваша реферальная ссылка</p>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={data?.link ?? ""}
            className="flex-1 h-9 px-3 text-sm bg-gray-50 border border-gray-200 rounded text-gray-800 focus:outline-none select-all"
            onClick={(e) => (e.target as HTMLInputElement).select()}
          />
          <button
            onClick={handleCopy}
            className="h-9 px-3 flex items-center gap-1.5 text-sm font-medium border border-gray-200 rounded text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition-colors"
          >
            {copied ? (
              <><Check className="w-4 h-4 text-green-600" /> Скопировано</>
            ) : (
              <><Copy className="w-4 h-4" /> Копировать</>
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 mt-2">Ваш друг получит скидку 20% на первую оплату</p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="border border-gray-200 rounded-lg p-5 bg-white">
          <p className="text-xs text-gray-500 mb-1">Приглашено</p>
          <p className="text-3xl font-bold text-[#111827]">{data?.invited_count ?? 0}</p>
        </div>
        <div className="border border-gray-200 rounded-lg p-5 bg-white">
          <p className="text-xs text-gray-500 mb-1">Оплатили</p>
          <p className="text-3xl font-bold text-green-600">{data?.converted_count ?? 0}</p>
        </div>
      </div>

      {/* Invited table */}
      <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
        <div className="grid grid-cols-3 px-4 py-2.5 border-b border-gray-200 bg-gray-50">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Email</span>
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Статус</span>
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Дата регистрации</span>
        </div>

        {!data?.invited.length ? (
          <div className="flex flex-col items-center justify-center py-12 gap-2">
            <Users className="w-8 h-8 text-gray-300" />
            <p className="text-sm text-gray-500">Вы ещё никого не пригласили</p>
          </div>
        ) : (
          data.invited.map((inv, idx) => (
            <div
              key={idx}
              className="grid grid-cols-3 px-4 py-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50 transition-colors"
            >
              <span className="text-sm text-gray-800 truncate">{maskEmail(inv.email)}</span>
              <span><StatusBadge status={inv.status} /></span>
              <span className="text-sm text-gray-500">
                {new Date(inv.registered_at).toLocaleDateString("ru-RU")}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
