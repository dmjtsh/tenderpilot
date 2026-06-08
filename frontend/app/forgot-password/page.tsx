"use client"

import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { authApi } from "@/lib/api"
import { ArrowLeft } from "lucide-react"

const schema = z.object({
  email: z.string().email("Некорректный email"),
})

type Form = z.infer<typeof schema>

const inputCls = "w-full h-8 rounded-md bg-secondary border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"

export default function ForgotPasswordPage() {
  const [sent, setSent] = useState(false)
  const [error, setError] = useState("")
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Form>({
    resolver: zodResolver(schema),
  })

  async function onSubmit(data: Form) {
    setError("")
    try {
      await authApi.passwordResetRequest(data.email)
      setSent(true)
    } catch {
      setError("Сервер недоступен. Попробуйте позже.")
    }
  }

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

        {sent ? (
          <div className="space-y-3 text-center">
            <p className="text-sm text-foreground">
              Если аккаунт с этим email существует, мы отправили письмо со ссылкой для сброса пароля.
            </p>
            <a href="/login" className="text-sm text-violet-600 hover:text-violet-700 transition-colors">
              Вернуться ко входу
            </a>
          </div>
        ) : (
          <>
            <h1 className="text-base font-semibold text-center mb-5">Сброс пароля</h1>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
              <div className="space-y-1.5">
                <label className="block text-xs text-muted-foreground font-medium">Email</label>
                <input className={inputCls} type="email" placeholder="you@company.com" {...register("email")} />
                {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
              </div>
              {error && <p className="text-xs text-destructive">{error}</p>}
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full h-8 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {isSubmitting ? "Отправка..." : "Отправить ссылку"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
