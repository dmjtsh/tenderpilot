"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useQueryClient } from "@tanstack/react-query"
import { authApi } from "@/lib/api"
import { setTokens, isAuthenticated } from "@/lib/auth"
import Image from "next/image"

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
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
  })

  async function onSubmit(data: LoginForm) {
    setError("")
    try {
      const res = await authApi.login(data.email, data.password)
      setTokens(res.access, res.refresh)
      onSuccess()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } }; code?: string }
      if (!err.response) {
        setError("Сервер недоступен. Запустите backend (manage.py runserver 8080)")
      } else {
        setError(err.response.data?.detail ?? "Неверный email или пароль")
      }
    }
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
      <Field label="Email" error={errors.email?.message}>
        <input className={inputCls} type="email" placeholder="you@company.com" {...register("email")} />
      </Field>
      <Field label="Пароль" error={errors.password?.message}>
        <input className={inputCls} type="password" placeholder="••••••••" {...register("password")} />
      </Field>
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

function RegisterTab({ onSuccess }: { onSuccess: () => void }) {
  const [error, setError] = useState("")
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<RegisterForm>({
    resolver: zodResolver(registerSchema),
  })

  async function onSubmit(data: RegisterForm) {
    setError("")
    try {
      const res = await authApi.register(data)
      setTokens(res.access, res.refresh)
      onSuccess()
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

export default function LoginPage() {
  const router = useRouter()
  const qc = useQueryClient()
  const [tab, setTab] = useState<"login" | "register">("login")

  useEffect(() => {
    if (isAuthenticated()) router.replace("/tenders")
  }, [router])

  const handleSuccess = () => { qc.clear(); localStorage.removeItem("onboarding_dismissed"); router.push("/tenders") }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-[360px]">
        {/* Logo */}
        <div className="flex items-center justify-center gap-2.5 mb-8">
          <Image src="/new_logo.jpg" width={26} height={26} className="rounded-xl" alt="TendeRoll" />
          <span className="text-lg font-semibold tracking-tight">TendeRoll</span>
        </div>

        {/* Tab switcher */}
        <div className="flex rounded-lg bg-secondary p-0.5 mb-5">
          {(["login", "register"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
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
          <RegisterTab onSuccess={handleSuccess} />
        )}
      </div>
    </div>
  )
}
