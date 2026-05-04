"use client"

import { Building2, Heart, Monitor, Cog, TreePine, ClipboardList } from "lucide-react"
import { useScrollAnimation } from "@/hooks/use-scroll-animation"

const industries = [
  {
    icon: Building2,
    name: "Строительство",
    description: "кровля, дороги, капремонт",
  },
  {
    icon: Heart,
    name: "Медицина",
    description: "оборудование, расходники",
  },
  {
    icon: Monitor,
    name: "IT",
    description: "ПО, инфраструктура, разработка",
  },
  {
    icon: Cog,
    name: "Производство",
    description: "оборудование, материалы",
  },
  {
    icon: TreePine,
    name: "Благоустройство",
    description: "парки, озеленение",
  },
  {
    icon: ClipboardList,
    name: "Услуги",
    description: "консалтинг, обслуживание",
  },
]

export function Industries() {
  const { ref, isVisible } = useScrollAnimation()

  return (
    <section id="industries" className="bg-white py-16 sm:py-24" ref={ref}>
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className={`text-center scroll-hidden ${isVisible ? "scroll-visible" : ""}`}>
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Подходит для любой отрасли
          </h2>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {industries.map((industry, index) => (
            <div
              key={industry.name}
              className={`border-2 border-[#D1D5DB] bg-[#F3F4F6] p-6 transition-all hover:border-[#111827] hover:shadow-sm hover:-translate-y-1 scroll-hidden-scale stagger-${index + 1} ${isVisible ? "scroll-visible" : ""}`}
            >
              <div className="flex h-12 w-12 items-center justify-center border border-[#D1D5DB] bg-white">
                <industry.icon className="h-6 w-6 text-[#111827]" />
              </div>
              <h3 className="mt-4 text-lg font-semibold text-[#111827]">
                {industry.name}
              </h3>
              <p className="mt-1 text-sm text-[#6B7280]">{industry.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
