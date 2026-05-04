"use client"

import { UserCircle, Bell, FileSearch, MessageSquare, CheckCircle } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const steps = [
  {
    number: "01",
    icon: UserCircle,
    title: "Настройте профиль",
    description: "Укажите направления деятельности, регионы и диапазон НМЦ",
  },
  {
    number: "02",
    icon: Bell,
    title: "Получайте тендеры",
    description: "ИИ автоматически подберёт релевантные закупки под ваш профиль",
  },
  {
    number: "03",
    icon: FileSearch,
    title: "Анализируйте документы",
    description: "Получите резюме, требования и риски за 30 секунд",
  },
  {
    number: "04",
    icon: MessageSquare,
    title: "Задавайте вопросы",
    description: "Спросите нейросеть о любом пункте документации и получите ответ с источником",
  },
  {
    number: "05",
    icon: CheckCircle,
    title: "Принимайте решения",
    description: "Оценивайте шансы на победу и участвуйте в лучших тендерах",
  },
]

export function HowItWorks() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section className="bg-[#F3F4F6] py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className={`text-center scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Как это работает
          </h2>
        </div>

        <div className="relative mt-16">
          <div className="absolute left-0 right-0 top-8 hidden h-0.5 bg-[#D1D5DB] md:block" />

          <div className="grid grid-cols-1 gap-8 md:grid-cols-5 md:gap-4">
            {steps.map((step, index) => (
              <div
                key={step.number}
                className={`relative text-center scroll-hidden-scale stagger-${index + 1} ${isVisible ? "scroll-visible" : ""}`}
              >
                <div className="relative mx-auto flex h-16 w-16 items-center justify-center border-2 border-[#D1D5DB] bg-white">
                  <step.icon className="h-6 w-6 text-[#111827]" />
                  <span className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center bg-[#111827] text-xs font-medium text-white">
                    {index + 1}
                  </span>
                </div>

                <h3 className="mt-6 text-lg font-semibold text-[#111827]">
                  {step.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">
                  {step.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
