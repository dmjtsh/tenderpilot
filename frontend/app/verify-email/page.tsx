"use client"

import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useQueryClient } from "@tanstack/react-query"
import { authApi } from "@/lib/api"
import { setTokens } from "@/lib/auth"
import { CheckCircle2, XCircle, Loader2 } from "lucide-react"

function VerifyEmailInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const qc = useQueryClient()
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading")
  const [errorMsg, setErrorMsg] = useState("")
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)

  const uid = searchParams.get("uid") || ""
  const token = searchParams.get("token") || ""

  useEffect(() => {
    if (!uid || !token) {
      setStatus("error")
      setErrorMsg("Некорректная ссылка")
      return
    }

    authApi.verifyEmail(uid, token).then((data) => {
      setTokens(data.access, data.refresh)
      qc.clear()
      setStatus("success")
      setTimeout(() => router.push("/tenders"), 1500)
    }).catch((e) => {
      const err = e as { response?: { data?: { error?: string } } }
      setStatus("error")
      setErrorMsg(err.response?.data?.error || "Недействительная или устаревшая ссылка")
    })
  }, [uid, token, router, qc])

  async function handleResend() {
    const email = prompt("Введите ваш email:")
    if (!email) return
    setResending(true)
    try {
      await authApi.resendVerification(email)
      setResent(true)
    } catch {
      // ignore
    } finally {
      setResending(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-[360px] text-center space-y-4">
        <a href="/" className="flex items-center justify-center gap-2.5 mb-8">
          <img src="/logo.svg" width={26} height={26} alt="TendeRoll" />
          <span className="text-lg font-semibold tracking-tight">TendeRoll</span>
        </a>

        {status === "loading" && (
          <>
            <Loader2 className="w-8 h-8 text-muted-foreground animate-spin mx-auto" />
            <p className="text-sm text-muted-foreground">Подтверждение email...</p>
          </>
        )}

        {status === "success" && (
          <>
            <div className="mx-auto w-10 h-10 rounded-full bg-green-50 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5 text-green-600" />
            </div>
            <p className="text-sm font-medium text-foreground">Email подтверждён</p>
            <p className="text-xs text-muted-foreground">Перенаправляем...</p>
          </>
        )}

        {status === "error" && (
          <>
            <div className="mx-auto w-10 h-10 rounded-full bg-red-50 flex items-center justify-center">
              <XCircle className="w-5 h-5 text-red-600" />
            </div>
            <p className="text-sm font-medium text-foreground">{errorMsg}</p>
            <button
              onClick={handleResend}
              disabled={resending || resent}
              className="text-xs text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
            >
              {resent ? "Письмо отправлено" : resending ? "Отправка..." : "Отправить новое письмо"}
            </button>
            <a href="/login" className="block text-xs text-muted-foreground hover:text-foreground transition-colors">
              Вернуться к входу
            </a>
          </>
        )}
      </div>
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense>
      <VerifyEmailInner />
    </Suspense>
  )
}
