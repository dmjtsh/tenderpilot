"use client"

import { useState } from "react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const faqs = [
  {
    question: "Какие площадки охватывает ТендерПилот?",
    answer:
      "Мы отслеживаем все федеральные площадки госзакупок: ЕИС, Сбербанк-АСТ, РТС-Тендер, Росэлторг и другие. Поддерживаем закупки по 44-ФЗ, 223-ФЗ и 615-ПП.",
  },
  {
    question: "Как работает ИИ-анализ документов?",
    answer:
      "ИИ читает техническое задание, проект контракта и другие документы закупки. Извлекает ключевые требования, сроки, штрафы и потенциальные риски. Также вы можете задавать вопросы нейросети по документам и получать точные ответы с указанием источника.",
  },
  {
    question: "Насколько точно ИИ подбирает тендеры?",
    answer:
      "Мы используем семантический поиск на основе нейросетей, а не простое совпадение по ключевым словам. Вы настраиваете направления с ОКВЭД, регионами и диапазоном НМЦ, и система подбирает тендеры по смыслу вашей деятельности.",
  },
  {
    question: "Есть ли пробный период?",
    answer:
      "Да, мы предлагаем 7 дней бесплатного доступа ко всем функциям платформы. Без привязки карты, просто зарегистрируйтесь и начните работать.",
  },
]

export function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section id="faq" className="bg-white py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className={`scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Есть вопросы?
          </h2>
          <p className="mt-2 text-base text-[#6B7280]">
            Ответили на самые частые из них
          </p>
        </div>

        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2">
          {faqs.map((faq, index) => {
            const isOpen = openIndex === index
            return (
              <button
                key={index}
                onClick={() => setOpenIndex(isOpen ? null : index)}
                className={`scroll-hidden-scale stagger-${index + 1} ${isVisible ? "scroll-visible" : ""} text-left p-6 border-2 transition-all duration-300 ${
                  isOpen
                    ? "border-[#111827] bg-white shadow-sm"
                    : "border-[#E5E7EB] bg-[#FAFAFA] hover:border-[#9CA3AF] hover:bg-white"
                }`}
              >
                <span className="text-xs font-mono text-[#9CA3AF]">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h3 className="mt-3 text-base font-semibold text-[#111827] leading-snug">
                  {faq.question}
                </h3>
                <div
                  className={`grid transition-all duration-300 ${
                    isOpen ? "grid-rows-[1fr] opacity-100 mt-3" : "grid-rows-[0fr] opacity-0"
                  }`}
                >
                  <div className="overflow-hidden">
                    <p className="text-sm leading-relaxed text-[#6B7280]">
                      {faq.answer}
                    </p>
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </section>
  )
}
