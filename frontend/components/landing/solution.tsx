"use client"

import { ArrowRight, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const facts = [
  {
    title: "Все площадки в одной ленте",
    text: <><strong>ЕИС, РТС, Сбер-АСТ, Росэлторг, Фабрикант</strong> плюс <strong>B2B-площадки</strong> (Бидзаар, B2B-Center, ОТС.Маркет). Один поиск, <strong>все тендеры</strong>.</>,
  },
  {
    title: "ИИ понимает деятельность вашей компании",
    text: <>По профилю компании ИИ определяет <strong>суть её деятельности</strong> и подбирает <strong>по-настоящему релевантные</strong> тендеры.</>,
  },
  {
    title: "AI-резюме за 10 секунд",
    text: <>Извлекает <strong>суть работ</strong>, <strong>условия оплаты</strong>, <strong>штрафы</strong>, <strong>гарантийные обязательства</strong> и <strong>красные флаги</strong> из всей документации.</>,
  },
  {
    title: "Чат с тендером",
    text: <>Спрашиваете напрямую, получаете ответ с <strong>цитатой из конкретного пункта</strong> документа.</>,
  },
]

export function Solution() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section id="solution" className="bg-zinc-900 py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-12 lg:flex-row lg:items-center lg:gap-16">
          <div className={`flex-1 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
            <h2 className="text-4xl font-bold tracking-tight text-white sm:text-5xl">
              <span className="font-serif italic">ТендерПилот делает это за вас</span>
            </h2>
            <p className="mt-6 text-lg leading-relaxed text-gray-300 [&_strong]:text-white [&_strong]:font-semibold">
              ИИ читает <strong>200 страниц</strong> ТЗ за <strong>10 секунд</strong>, находит <strong>подводные камни</strong>,
              подбирает тендеры под профиль вашего бизнеса и отвечает на любые
              вопросы по документации.
            </p>
            <div className="mt-10">
              <Link href="/login">
                <Button className="rounded-none bg-white px-8 py-3 text-lg text-gray-900 hover:bg-gray-100 btn-hover-lift h-auto">
                  Начать бесплатно
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Button>
              </Link>
            </div>
          </div>

          <div className={`flex-1 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
            <div className="aspect-video rounded-2xl border border-zinc-600 bg-gradient-to-br from-zinc-800 to-zinc-700 flex flex-col items-center justify-center gap-3">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-white/10 backdrop-blur-sm">
                <Play className="h-7 w-7 text-white fill-white" />
              </div>
              <span className="text-sm font-medium text-gray-400">Демо скоро</span>
            </div>
          </div>
        </div>

        <div className="mt-16 grid grid-cols-1 gap-6 sm:grid-cols-2">
          {facts.map((fact, index) => (
            <div
              key={fact.title}
              className={`flex gap-4 rounded-lg border border-zinc-700 bg-zinc-800 p-6 scroll-hidden stagger-${index + 1} ${isVisible ? "scroll-visible" : ""}`}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10">
                <ArrowRight className="h-4 w-4 text-white" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-white">
                  {fact.title}
                </h3>
                <p className="mt-2 text-base leading-relaxed text-gray-300 [&_strong]:text-white [&_strong]:font-semibold">
                  {fact.text}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
