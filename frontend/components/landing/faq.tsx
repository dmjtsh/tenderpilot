"use client"

import { useState } from "react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const faqs = [
  {
    question: "Какие площадки охватывает ТендерПилот?",
    answer:
      "Все федеральные площадки госзакупок: ЕИС, Сбербанк-АСТ, РТС-Тендер, Росэлторг, Фабрикант. Поддерживаем закупки по 44-ФЗ, 223-ФЗ и 615-ПП. Также работаем с B2B-площадками: Бидзаар, B2B-Center, ОТС.Маркет, где публикуются коммерческие тендеры.",
  },
  {
    question: "Насколько точно ИИ подбирает тендеры?",
    answer:
      "Мы используем семантический поиск, а не простое совпадение по ключевым словам. Вы настраиваете направления с ОКВЭД, регионами и диапазоном НМЦК, и система подбирает тендеры по смыслу вашей деятельности. Чем точнее заполнен профиль, тем релевантнее подборка.",
  },
  {
    question: "Что если ИИ ошибётся в анализе документов?",
    answer:
      "AI-резюме это помощник, а не замена юристу. Мы всегда показываем источник: каждый факт в резюме можно проверить через чат с тендером, который даёт ответ с цитатой из конкретного документа. Финальное решение всегда за вами.",
  },
  {
    question: "Безопасно ли загружать данные в ТендерПилот?",
    answer:
      "Мы не запрашиваем конфиденциальные данные вашей компании. Профиль содержит только открытую информацию: ИНН, направления деятельности, регионы. Документы тендеров это публичная информация с площадок госзакупок.",
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
            Частые вопросы о поиске тендеров
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
