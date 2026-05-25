"use client"

import Image from "next/image"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const demos = [
  {
    imageSrc: "/screenshot-summary.png",
    imageAlt: "AI-резюме тендера",
    caption: "Это резюме настоящего тендера на 991 793 \u20BD. AI нашёл фактического заказчика (детский сад), штраф 99 179 \u20BD при цене до 3 млн рублей, требование паспортных данных персонала. Всё за 10 секунд.",
  },
  {
    imageSrc: "/screenshot-chat.png",
    imageAlt: "Чат с тендером",
    caption: "Спросили \u00ABкакие сроки?\u00BB и получили ответ с цитатой из пункта контракта.",
  },
  {
    imageSrc: "/screenshot-pipeline.png",
    imageAlt: "Pipeline Kanban",
    caption: "Все ваши тендеры в одной канбан-доске. От \u00ABИзучаю\u00BB до \u00ABВыиграл\u00BB.",
  },
]

export function Features() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section id="product" className="bg-white py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className={`text-center scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Реальный пример работы
          </h2>
        </div>

        <div className="mt-16 space-y-20">
          {demos.map((demo, index) => (
            <div
              key={demo.imageSrc}
              className={`scroll-hidden stagger-${index + 1} ${isVisible ? "scroll-visible" : ""}`}
            >
              <div className="overflow-hidden rounded-lg border border-[#E5E7EB] shadow-lg">
                <Image
                  src={demo.imageSrc}
                  alt={demo.imageAlt}
                  width={1200}
                  height={750}
                  className="w-full"
                />
              </div>
              <p className="mx-auto mt-6 max-w-2xl text-center text-base leading-relaxed text-[#6B7280]">
                {demo.caption}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
