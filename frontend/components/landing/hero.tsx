"use client"

import { ArrowRight, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import Image from "next/image"
import Link from "next/link"

const stats = [
  { value: "5 000+", label: "тендеров анализируется ежедневно" },
  { value: "30 сек", label: "ИИ читает 200 страниц ТЗ за вас" },
  { value: "24/7", label: "нейросеть ищет тендеры пока вы спите" },
]

export function Hero() {
  return (
    <section className="bg-white px-4 pb-16 pt-16 sm:px-6 sm:pb-24 sm:pt-24 lg:px-8">
      <div className="mx-auto max-w-7xl">
        {/* Headline */}
        <div className="mx-auto max-w-3xl text-center animate-hero" style={{ animationDelay: "0.15s" }}>
          <h1 className="text-4xl font-bold tracking-tight text-[#111827] sm:text-5xl lg:text-6xl">
            <span className="text-balance">Находите нужные тендеры.</span>
            <br />
            <span className="font-serif italic text-[#111827]">Пока конкуренты ищут вручную.</span>
          </h1>
        </div>

        {/* Subtext */}
        <p className="mx-auto mt-6 max-w-2xl text-center text-lg leading-relaxed text-[#6B7280] animate-hero" style={{ animationDelay: "0.3s" }}>
          <span className="font-semibold text-[#111827]">Первый ИИ-анализатор тендеров в России.</span>
          <br />
          Анализирует рынок госзакупок и подбирает тендеры под профиль вашей компании.
          Документация, резюме и риски за секунды.
        </p>

        {/* CTA Buttons */}
        <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row animate-hero" style={{ animationDelay: "0.45s" }}>
          <Link href="/login">
            <Button size="lg" className="rounded-none bg-[#111827] text-white hover:bg-[#1f2937] btn-hover-lift">
              Начать бесплатно
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
          <a href="#features">
            <Button
              size="lg"
              variant="outline"
              className="rounded-none border-[#D1D5DB] bg-white text-[#374151] hover:bg-[#F3F4F6] btn-hover-lift"
            >
              <Play className="mr-2 h-4 w-4" />
              Смотреть демо
            </Button>
          </a>
        </div>


        {/* Image + Stats */}
        <div className="mx-auto mt-16 max-w-5xl animate-hero" style={{ animationDelay: "0.6s" }}>
          <div className="flex flex-col items-center gap-10 lg:flex-row lg:items-center lg:justify-between">
            {/* Stats column */}
            <div className="flex flex-col justify-center gap-8">
              {stats.map((stat, i) => (
                <div key={i} className="text-center lg:text-left">
                  <div className="text-4xl font-bold tracking-tight text-[#111827] sm:text-5xl">
                    {stat.value}
                  </div>
                  <div className="mt-1 text-base text-[#6B7280]">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>

            {/* Image */}
            <div className="shrink-0">
              <Image
                src="/hero.png"
                alt="ИИ-анализ тендеров"
                width={700}
                height={700}
                className="w-[500px] -mr-8"
                priority
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
