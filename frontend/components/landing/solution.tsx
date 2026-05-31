"use client"

import { ArrowRight, Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"
import { useRef, useState } from "react"

const facts = [
  {
    title: "Все площадки в одной ленте",
    text: "ЕИС, РТС, Сбер-АСТ, Росэлторг, Фабрикант плюс B2B-площадки (Бидзаар, B2B-Center, ОТС.Маркет). Один поиск, все тендеры.",
  },
  {
    title: "ИИ понимает деятельность вашей компании",
    text: "По профилю компании ИИ определяет суть её деятельности и подбирает по-настоящему релевантные тендеры.",
  },
  {
    title: "AI-резюме за 10 секунд",
    text: "Извлекает суть работ, условия оплаты, штрафы, гарантийные обязательства и красные флаги из всей документации.",
  },
  {
    title: "Чат с тендером",
    text: "Спрашиваете напрямую, получаете ответ с цитатой из конкретного пункта документа.",
  },
]

export function Solution() {
  const { ref, isVisible } = useScrollAnimation()
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)

  function handlePlay() {
    videoRef.current?.play()
    setPlaying(true)
  }

  function handleVideoClick() {
    const v = videoRef.current
    if (!v) return
    if (v.paused) { v.play() } else { v.pause() }
  }

  return (
    <section id="solution" className="bg-zinc-900 py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-12 lg:flex-row lg:items-center lg:gap-16">
          <div className={`flex-1 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
            <h2 className="text-4xl font-bold tracking-tight text-white sm:text-5xl">
              <span className="font-serif italic">TendeRoll делает это за вас</span>
            </h2>
            <p className="mt-6 text-lg leading-relaxed text-gray-300">
              ИИ читает 200 страниц ТЗ за 10 секунд, находит подводные камни,
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

          <div id="demo" className={`flex-1 scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
            <div className="relative overflow-hidden rounded-2xl border border-zinc-600">
              <video
                ref={videoRef}
                src="/demo.mp4"
                preload="none"
                poster="/demo-poster.jpg"
                controls={playing}
                playsInline
                onClick={handleVideoClick}
                onEnded={() => setPlaying(false)}
                className="w-full aspect-video bg-zinc-900 cursor-pointer"
              />
              {!playing && (
                <button
                  onClick={handlePlay}
                  aria-label="Смотреть демо"
                  className="absolute inset-0 flex items-center justify-center bg-black/40 hover:bg-black/50 transition-colors group"
                >
                  <span className="flex h-16 w-16 items-center justify-center rounded-full bg-white/20 backdrop-blur-sm transition-transform group-hover:scale-110 border border-white/30">
                    <Play className="h-7 w-7 translate-x-0.5 text-white fill-white" />
                  </span>
                </button>
              )}
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
                <p className="mt-2 text-base leading-relaxed text-gray-300">
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
