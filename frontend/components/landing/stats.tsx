"use client"

import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const stats = [
  { value: "5 000+", label: "тендеров анализируется ежедневно" },
  { value: "30 сек", label: "ИИ читает 200 страниц ТЗ за вас" },
  { value: "24/7", label: "нейросеть ищет тендеры пока вы спите" },
]

export function Stats() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section className="bg-white py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-3 md:gap-0 md:divide-x md:divide-[#E5E7EB]">
          {stats.map((stat, index) => (
            <div
              key={index}
              className={`text-center md:px-8 scroll-hidden stagger-${index + 1} ${isVisible ? "scroll-visible" : ""}`}
            >
              <div className="text-4xl font-bold tracking-tight text-[#111827] sm:text-5xl">
                {stat.value}
              </div>
              <div className="mt-2 text-base text-[#6B7280]">
                {stat.label}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
