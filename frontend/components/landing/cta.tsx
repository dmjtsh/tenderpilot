"use client"

import { useEffect, useState } from "react"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import Image from "next/image"
import Link from "next/link"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"
import { isAuthenticated } from "@/lib/auth"

export function CTA() {
  const { ref, isVisible } = useScrollAnimation()
  const [authed, setAuthed] = useState(false)

  useEffect(() => {
    setAuthed(isAuthenticated())
  }, [])

  if (authed) return null

  return (
    <section className="bg-[#111827] py-16 sm:py-24" ref={ref}>
      <div className={`mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
        <div className="flex flex-col items-center gap-10 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-2xl text-center lg:text-left">
            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
              Каждый день в Excel это упущенные тендеры и потерянная прибыль.
            </h2>
            <div className="mt-8">
              <Link href="/login">
                <Button
                  size="lg"
                  className="rounded-none bg-white text-[#111827] hover:bg-gray-100 btn-hover-lift"
                >
                  Начать бесплатно
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
            <p className="mt-4 text-base text-gray-400">
              7 дней без оплаты. Без привязки карты.
            </p>
          </div>

          <div className="hidden shrink-0 lg:block">
            <Image
              src="/sculptures/tomes.png"
              alt=""
              width={240}
              height={240}
              className="w-[180px] sm:w-[200px] lg:w-[240px] opacity-90"
            />
          </div>
        </div>
      </div>
    </section>
  )
}
