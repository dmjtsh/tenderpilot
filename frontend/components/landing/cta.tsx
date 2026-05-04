"use client"

import { useEffect, useState } from "react"
import { ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"
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
      <div className={`mx-auto max-w-4xl px-4 text-center sm:px-6 lg:px-8 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
        <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">
          Начните находить нужные тендеры сегодня
        </h2>
        <p className="mt-4 text-lg text-gray-300">
          7 дней бесплатно. Без привязки карты. Отмена в любой момент.
        </p>
        <div className="mt-8">
          <Link href="/login">
            <Button
              size="lg"
              className="rounded-none bg-white text-[#111827] hover:bg-gray-100 btn-hover-lift"
            >
              Попробовать бесплатно
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    </section>
  )
}
