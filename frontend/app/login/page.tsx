"use client"

import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useQueryClient } from "@tanstack/react-query"
import { authApi } from "@/lib/api"
import { setTokens, isAuthenticated } from "@/lib/auth"
import { trackGoal } from "@/lib/analytics"
import { ArrowLeft, Mail } from "lucide-react"

const loginSchema = z.object({
  email: z.string().email("Некорректный email"),
  password: z.string().min(1, "Введите пароль"),
})

const registerSchema = z.object({
  email: z.string().email("Некорректный email"),
  first_name: z.string().optional(),
  password: z.string().min(8, "Минимум 8 символов"),
  password2: z.string(),
}).refine((d) => d.password === d.password2, {
  message: "Пароли не совпадают",
  path: ["password2"],
})

type LoginForm = z.infer<typeof loginSchema>
type RegisterForm = z.infer<typeof registerSchema>

function Field({
  label, error, children,
}: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label className="block text-xs text-muted-foreground font-medium">{label}</label>
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

const inputCls = "w-full h-8 rounded-md bg-secondary border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"

function LoginTab({ onSuccess }: { onSuccess: () => void }) {
  const [error, setError] = useState("")
  const [unverifiedEmail, setUnverifiedEmail] = useState("")
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  })

  async function onSubmit(data: LoginForm) {
    setError("")
    setUnverifiedEmail("")
    try {
      const res = await authApi.login(data.email, data.password)
      setTokens(res.access, res.refresh)
      onSuccess()
    } catch (e: unknown) {
      const err = e as { response?: { status?: number; data?: { detail?: string; code?: string; error?: string } }; code?: string }
      if (!err.response) {
        setError("Сервер недоступен. Запустите backend (manage.py runserver 8080)")
      } else if (err.response.status === 403 && err.response.data?.code === "email_not_verified") {
        setUnverifiedEmail(data.email)
      } else {
        setError(err.response.data?.detail ?? "Неверный email или пароль")
      }
    }
  }

  async function handleResend() {
    if (!unverifiedEmail || resending) return
    setResending(true)
    try {
      await authApi.resendVerification(unverifiedEmail)
      setResent(true)
    } catch {
      setError("Не удалось отправить письмо")
    } finally {
      setResending(false)
    }
  }

  if (unverifiedEmail) {
    return (
      <div className="text-center space-y-4 py-4">
        <div className="mx-auto w-10 h-10 rounded-full bg-amber-50 flex items-center justify-center">
          <Mail className="w-5 h-5 text-amber-600" />
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">Email не подтверждён</p>
          <p className="text-xs text-muted-foreground mt-1">
            Проверьте почту <span className="font-medium">{unverifiedEmail}</span> и перейдите по ссылке для подтверждения
          </p>
        </div>
        <button
          onClick={handleResend}
          disabled={resending || resent}
          className="text-xs text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
        >
          {resent ? "Письмо отправлено" : resending ? "Отправка..." : "Отправить письмо повторно"}
        </button>
        <button
          onClick={() => { setUnverifiedEmail(""); setResent(false) }}
          className="block mx-auto text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Назад к входу
        </button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
      <Field label="Email" error={errors.email?.message}>
        <input className={inputCls} type="email" placeholder="you@company.com" {...register("email")} />
      </Field>
      <Field label="Пароль" error={errors.password?.message}>
        <input className={inputCls} type="password" placeholder="••••••••" {...register("password")} />
      </Field>
      <div className="flex justify-end">
        <a href="/forgot-password" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
          Забыли пароль?
        </a>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full h-8 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {isSubmitting ? "Вход..." : "Войти"}
      </button>
    </form>
  )
}

function RegisterTab({ refCode }: { refCode: string }) {
  const [error, setError] = useState("")
  const [registeredEmail, setRegisteredEmail] = useState("")
  const [resending, setResending] = useState(false)
  const [resent, setResent] = useState(false)
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  })

  async function onSubmit(data: RegisterForm) {
    setError("")
    try {
      await authApi.register({ ...data, ...(refCode ? { ref_code: refCode } : {}) })
      trackGoal("register_success")
      setRegisteredEmail(data.email)
    } catch (e: unknown) {
      const err = e as { response?: { data?: Record<string, string[]> } }
      if (!err.response) {
        setError("Сервер недоступен. Запустите backend (manage.py runserver 8080)")
      } else {
        const d = err.response.data
        setError(d ? Object.values(d).flat().join("; ") : "Ошибка регистрации")
      }
    }
  }

  async function handleResend() {
    if (!registeredEmail || resending) return
    setResending(true)
    try {
      await authApi.resendVerification(registeredEmail)
      setResent(true)
      setTimeout(() => setResent(false), 60_000)
    } catch {
      setError("Не удалось отправить письмо")
    } finally {
      setResending(false)
    }
  }

  if (registeredEmail) {
    return (
      <div className="text-center space-y-4 py-4">
        <div className="mx-auto w-10 h-10 rounded-full bg-violet-50 flex items-center justify-center">
          <Mail className="w-5 h-5 text-violet-600" />
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">Проверьте почту</p>
          <p className="text-xs text-muted-foreground mt-1">
            Мы отправили письмо на <span className="font-medium">{registeredEmail}</span>. Перейдите по ссылке для подтверждения.
          </p>
        </div>
        <button
          onClick={handleResend}
          disabled={resending || resent}
          className="text-xs text-primary hover:text-primary/80 transition-colors disabled:opacity-50"
        >
          {resent ? "Письмо отправлено" : resending ? "Отправка..." : "Отправить повторно"}
        </button>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
      <Field label="Email" error={errors.email?.message}>
        <input className={inputCls} type="email" placeholder="you@company.com" {...register("email")} />
      </Field>
      <Field label="Имя (необязательно)">
        <input className={inputCls} placeholder="Иван" {...register("first_name")} />
      </Field>
      <Field label="Пароль" error={errors.password?.message}>
        <input className={inputCls} type="password" placeholder="••••••••" {...register("password")} />
      </Field>
      <Field label="Повторите пароль" error={errors.password2?.message}>
        <input className={inputCls} type="password" placeholder="••••••••" {...register("password2")} />
      </Field>
      {error && <p className="text-xs text-destructive">{error}</p>}
      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full h-8 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {isSubmitting ? "Создание..." : "Зарегистрироваться"}
      </button>
    </form>
  )
}

function LoginPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const qc = useQueryClient()

  const urlRef = searchParams.get("ref")
  const [refCode, setRefCode] = useState<string>("")
  const [tab, setTab] = useState<"login" | "register">(() => urlRef ? "register" : "login")

  useEffect(() => {
    try {
      if (urlRef) {
        localStorage.setItem("ref_code", urlRef)
        setRefCode(urlRef)
      } else {
        const stored = localStorage.getItem("ref_code") ?? ""
        setRefCode(stored)
      }
    } catch {
      // private browsing mode
    }
  }, [urlRef])

  const redirectTo = searchParams.get("redirect") || "/tenders"

  useEffect(() => {
    if (isAuthenticated()) router.replace(redirectTo)
  }, [router, redirectTo])

  const handleSuccess = () => {
    qc.clear()
    localStorage.removeItem("onboarding_dismissed")
    try { localStorage.removeItem("ref_code") } catch { /* ignore */ }
    router.push(redirectTo)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 relative">
      <button
        onClick={() => window.history.back()}
        className="absolute top-6 left-6 flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#111827] transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Назад
      </button>
      <div className="w-full max-w-[360px]">
        {/* Logo */}
        <a href="/" className="flex items-center justify-center gap-2.5 mb-8">
          <img src="/logo.svg" width={26} height={26} alt="TendeRoll" />
          <span className="text-lg font-semibold tracking-tight">TendeRoll</span>
        </a>

        {/* Tab switcher */}
        <div className="flex rounded-lg bg-secondary p-0.5 mb-5">
          {(["login", "register"] as const).map((t) => (
            <button
              key={t}
              onClick={() => { if (t === "register") trackGoal("viewed_register"); setTab(t) }}
              className={`flex-1 h-7 text-xs font-medium rounded-md transition-colors ${
                tab === t
                  ? "bg-background text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {t === "login" ? "Войти" : "Регистрация"}
            </button>
          ))}
        </div>

        {/* Form */}
        {tab === "login" ? (
          <LoginTab onSuccess={handleSuccess} />
        ) : (
          <RegisterTab refCode={refCode} />
        )}
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPageInner />
    </Suspense>
  )
}
