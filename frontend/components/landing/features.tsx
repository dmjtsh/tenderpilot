"use client"

import { Search, FileText, MessageSquare } from "lucide-react"
import Image from "next/image"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const features = [
  {
    tag: "Умный поиск",
    tagIcon: Search,
    title: "ИИ подбирает тендеры под вашу компанию",
    description:
      "Не просто ключевые слова. Семантический поиск понимает суть деятельности компании. Настройте направления с НМЦ и регионами, получайте только релевантное.",
    imagePosition: "right" as const,
    imageSrc: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&h=450&fit=crop",
    imageAlt: "Анализ тендерной документации за ноутбуком",
  },
  {
    tag: "Анализ документов",
    tagIcon: FileText,
    title: "Резюме тендера за 30 секунд",
    description:
      "ИИ читает техническое задание, проект контракта и другие документы закупки. Извлекает ключевые требования, сроки, штрафы и потенциальные риски.",
    imagePosition: "left" as const,
    imageSrc: "https://images.unsplash.com/photo-1568234928966-359c35dd8327?w=600&h=450&fit=crop",
    imageAlt: "Анализ документов и отчётов",
  },
  {
    tag: "RAG чат",
    tagIcon: MessageSquare,
    title: "Задайте вопрос документу",
    description:
      "Не можете найти нужный пункт? Просто спросите, и ИИ найдёт ответ и покажет источник в документе.",
    imagePosition: "right" as const,
    imageSrc: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=600&h=450&fit=crop",
    imageAlt: "Интеллектуальный поиск по документам",
  },
]

function FeatureBlock({ feature }: { feature: (typeof features)[number] }) {
  const { ref, isVisible } = useScrollAnimation()
  const textDir = feature.imagePosition === "right" ? "scroll-hidden-left" : "scroll-hidden-right"
  const imgDir = feature.imagePosition === "right" ? "scroll-hidden-right" : "scroll-hidden-left"

  return (
    <div
      ref={ref}
      className={`flex flex-col items-center gap-12 lg:flex-row lg:gap-16 ${
        feature.imagePosition === "left" ? "lg:flex-row-reverse" : ""
      }`}
    >
      <div className={`flex-1 ${textDir} ${isVisible ? "scroll-visible" : ""}`}>
        <div className="inline-flex items-center gap-2 border border-[#D1D5DB] bg-[#F3F4F6] px-3 py-1">
          <feature.tagIcon className="h-4 w-4 text-[#374151]" />
          <span className="text-sm font-medium text-[#374151]">{feature.tag}</span>
        </div>
        <h3 className="mt-6 text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
          {feature.title}
        </h3>
        <p className="mt-4 text-lg leading-relaxed text-[#6B7280]">
          {feature.description}
        </p>
      </div>

      <div className={`flex-1 ${imgDir} ${isVisible ? "scroll-visible" : ""}`}>
        <div className="border-2 border-[#D1D5DB] bg-[#F3F4F6] p-1">
          <Image
            src={feature.imageSrc}
            alt={feature.imageAlt}
            width={600}
            height={450}
            className="w-full"
          />
        </div>
      </div>
    </div>
  )
}

export function Features() {
  return (
    <section id="features" className="bg-white py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="space-y-24">
          {features.map((feature) => (
            <FeatureBlock key={feature.tag} feature={feature} />
          ))}
        </div>
      </div>
    </section>
  )
}
