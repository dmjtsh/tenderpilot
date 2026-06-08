"use client"

import { useState, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { authApi } from "@/lib/api"
import { ArrowLeft } from "lucide-react"

const schema = z.object({
  new_password: z.string().min(8, "Минимум 8 символов"),
  confirm_password: z.string(),
}).refine((d) => d.new_password === d.confirm_password, {
  message: "Пароли не совпадают",
  path: ["confirm_password"],
})

type Form = z.infer<typeof schema>

const inputCls = "w-full h-8 rounded-md bg-secondary border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"

function ResetForm() {
  const searchParams = useSearchParams()
  const uid = searchParams.get("uid")
  const token = searchParams.get("token")

  const [done, setDone] = useState(false)
  const [error, setError] = useState("")
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Form>({
    resolver: zodResolver(schema),
  })

  if (!uid || !token) {
    return (
      <div className="space-y-3 text-center">
        <p className="text-sm text-destructive">Недействительная ссылка. Запросите сброс пароля повторно.</p>
        <a href="/forgot-password" className="text-sm text-violet-600 hover:text-violet-700 transition-colors">
          Сбросить пароль
        </a>
      </div>
    )
  }

  async function onSubmit(data: Form) {
    setError("")
    try {
      const res = await authApi.passwordResetConfirm(uid!, token!, data.new_password)
      if (res.error) {
        setError(res.error)
      } else {
        setDone(true)
      }
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } }
      setError(err.response?.data?.error ?? "Произошла ошибка. Попробуйте позже.")
    }
  }

  if (done) {
    return (
      <div className="space-y-3 text-center">
        <p className="text-sm text-foreground">Пароль успешно изменён.</p>
        <a href="/login" className="text-sm text-violet-600 hover:text-violet-700 transition-colors">
          Войти
        </a>
      </div>
    )
  }

  return (
    <>
      <h1 className="text-base font-semibold text-center mb-5">Новый пароль</h1>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
        <div className="space-y-1.5">
          <label className="block text-xs text-muted-foreground font-medium">Новый пароль</label>
          <input className={inputCls} type="password" placeholder="••••••••" {...register("new_password")} />
          {errors.new_password && <p className="text-xs text-destructive">{errors.new_password.message}</p>}
        </div>
        <div className="space-y-1.5">
          <label className="block text-xs text-muted-foreground font-medium">Повторите пароль</label>
          <input className={inputCls} type="password" placeholder="••••••••" {...register("confirm_password")} />
          {errors.confirm_password && <p className="text-xs text-destructive">{errors.confirm_password.message}</p>}
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full h-8 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {isSubmitting ? "Сохранение..." : "Сохранить пароль"}
        </button>
      </form>
    </>
  )
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 relative">
      <a
        href="/login"
        className="absolute top-6 left-6 flex items-center gap-1.5 text-sm text-gray-500 hover:text-[#111827] transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Назад
      </a>
      <div className="w-full max-w-[360px]">
        <a href="/" className="flex items-center justify-center gap-2.5 mb-8">
          <img src="/logo.svg" width={26} height={26} alt="TendeRoll" />
          <span className="text-lg font-semibold tracking-tight">TendeRoll</span>
        </a>
        <Suspense fallback={<div className="text-center text-sm text-muted-foreground">Загрузка...</div>}>
          <ResetForm />
        </Suspense>
      </div>
    </div>
  )
}
