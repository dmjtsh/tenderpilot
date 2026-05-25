"use client"

import Image from "next/image"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const pains = [
  {
    number: "01",
    title: "МНОГО ИСТОЧНИКОВ",
    text: "44-ФЗ и 223-ФЗ агрегирует zakupki.gov.ru. Но есть ещё B2B-площадки: Бидзаар, B2B-Center, ОТС.Маркет. На них публикуются коммерческие тендеры. Чтобы не упустить нужное, нужно следить за всеми сразу.",
  },
  {
    number: "02",
    title: "ПОДБОР ПОД ПРОФИЛЬ",
    text: "Возможностей поиска на классических площадках недостаточно, чтобы эффективно отбирать тендеры под конкретный бизнес. Из тысяч закупок приходится вручную просматривать сотни. Чтобы найти десяток действительно подходящих.",
  },
  {
    number: "03",
    title: "СОТНИ СТРАНИЦ",
    text: "ТЗ, проект контракта, требования к заявке, приложения. На один тендер десятки документов с сотнями страниц, и каждый нужно прочитать.",
  },
  {
    number: "04",
    title: "ПОДВОДНЫЕ КАМНИ",
    text: "Обеспечение 30%, штрафы за нарушение сроков, гарантийные обязательства на 5 лет. Один пропущенный пункт, и тендер становится убыточным.",
  },
]

export function PainPoints() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section className="bg-white py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-12 lg:flex-row lg:items-center lg:gap-16">
          <div className="flex-1">
            <div className={`scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
              <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
                Поиск тендеров вручную: непростое и времязатратное занятие
              </h2>
              <p className="mt-4 text-lg text-[#6B7280]">
                Вот с чем приходится иметь дело
              </p>
            </div>

            <div className="mt-10 grid grid-cols-1 gap-5 sm:grid-cols-2">
              {pains.map((pain, index) => (
                <div
                  key={pain.title}
                  className={`relative overflow-hidden border border-[#E5E7EB] border-l-4 border-l-[#111827] bg-white p-6 transition-all duration-200 hover:border-[#6B7280] hover:shadow-md scroll-hidden-scale stagger-${index + 1} ${isVisible ? "scroll-visible" : ""}`}
                >
                  <span className="absolute right-3 top-2 text-7xl font-bold leading-none text-[#111827]/[0.08]">
                    {pain.number}
                  </span>
                  <h3 className="pr-20 text-xl font-bold tracking-wide text-[#111827]">
                    {pain.title}
                  </h3>
                  <p className="mt-3 pr-20 text-[15px] leading-relaxed text-[#374151]">
                    {pain.text}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="hidden shrink-0 lg:flex lg:items-center">
            <Image
              src="/sculptures/tomes.png"
              alt="Стопка тендерной документации"
              width={320}
              height={320}
              className="w-[280px] lg:w-[320px] max-h-[520px] object-contain"
            />
          </div>
        </div>
      </div>
    </section>
  )
}
