"use client"

import Image from "next/image"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const steps = [
  {
    number: "1",
    title: "Заполните профиль компании",
    description: "Введите ИНН. Данные подтянутся автоматически из ФНС. Укажите направления деятельности и регионы интереса. Это займёт минуту.",
    image: "/sculptures/quill.png",
  },
  {
    number: "2",
    title: "Получайте подобранные тендеры",
    description: "ИИ ежедневно анализирует тысячи закупок со всех площадок и подбирает только релевантные вашему профилю.",
    image: "/sculptures/scales.png",
  },
  {
    number: "3",
    title: "Изучайте за минуты, а не часы",
    description: "Откройте тендер, AI-резюме готово. Возникли вопросы по документации? Спросите в чате. Решили участвовать? Добавьте в свой Pipeline.",
    image: "/sculptures/magnifier-scroll.png",
  },
]

export function HowItWorks() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section id="how-it-works" className="bg-white py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className={`text-center scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Как работает автоматический поиск тендеров
          </h2>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-12 md:grid-cols-3 md:gap-8">
          {steps.map((step, index) => (
            <div
              key={step.number}
              className={`text-center scroll-hidden-scale stagger-${index + 1} ${isVisible ? "scroll-visible" : ""}`}
            >
              <Image
                src={step.image}
                alt={step.title}
                width={220}
                height={220}
                className="mx-auto w-[180px] sm:w-[210px]"
              />

              <span className="mt-6 block text-3xl font-bold text-[#111827]">
                {step.number}
              </span>

              <h3 className="mt-3 text-lg font-semibold text-[#111827]">
                {step.title}
              </h3>
              <p className="mt-3 text-base leading-relaxed text-[#6B7280]">
                {step.description}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
