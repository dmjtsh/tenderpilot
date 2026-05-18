"use client"

import { ArrowRight, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import Image from "next/image"
import Link from "next/link"

export function Hero() {
  return (
    <section className="bg-white px-4 pb-16 pt-16 sm:px-6 sm:pb-20 sm:pt-24 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-col items-center gap-10 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-2xl text-center lg:text-left">
            <div className="animate-hero" style={{ animationDelay: "0.15s" }}>
              <h1 className="text-5xl font-bold tracking-tight leading-tight text-[#111827] sm:text-6xl lg:text-7xl">
                <span className="text-balance">ИИ-поиск тендеров и госзакупок.</span>
                <br />
                <span className="font-serif italic text-[#111827]">Пока конкуренты ищут вручную.</span>
              </h1>
            </div>

            <p className="mt-6 text-lg font-medium text-[#6B7280] animate-hero" style={{ animationDelay: "0.3s" }}>
              Первый ИИ-автоматизатор тендеров в России.
            </p>

            <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row lg:justify-start animate-hero" style={{ animationDelay: "0.45s" }}>
              <Link href="/login">
                <Button size="lg" className="rounded-none bg-[#111827] text-white hover:bg-[#1f2937] btn-hover-lift h-12 px-8 text-base font-semibold">
                  Начать бесплатно
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <a href="#solution">
                <Button
                  size="lg"
                  variant="outline"
                  className="rounded-none border-[#D1D5DB] bg-white text-[#374151] hover:bg-[#F3F4F6] btn-hover-lift h-12 px-8 text-base font-semibold"
                >
                  <Play className="mr-2 h-4 w-4" />
                  Смотреть демо
                </Button>
              </a>
            </div>
          </div>

          <div className="shrink-0 animate-hero" style={{ animationDelay: "0.6s" }}>
            <Image
              src="/sculptures/themis.png"
              alt="ТендерПилот"
              width={500}
              height={500}
              className="w-[300px] sm:w-[360px] lg:w-[450px]"
              priority
            />
          </div>
        </div>
      </div>
    </section>
  )
}
