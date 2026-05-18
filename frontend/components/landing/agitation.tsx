"use client"

import Image from "next/image"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

export function Agitation() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section className="bg-white py-16 sm:py-20" ref={ref}>
      <div className={`mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
        <div className="flex flex-col items-center gap-8 lg:flex-row lg:items-center lg:gap-16">
          <div className="shrink-0">
            <Image
              src="/sculptures/hourglass.png"
              alt="Время уходит на ручной поиск тендеров"
              width={240}
              height={240}
              className="w-[160px] sm:w-[200px] lg:w-[240px]"
            />
          </div>
          <div className="text-center lg:text-left">
            <p className="text-2xl font-semibold tracking-tight text-[#111827] sm:text-3xl">
              Поиск тендеров занимает половину рабочего дня.
            </p>
            <p className="mt-4 text-2xl italic text-[#111827] sm:text-3xl">
              Но что, если можно проще?
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
