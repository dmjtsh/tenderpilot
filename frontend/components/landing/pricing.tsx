import { Check } from "lucide-react"
import { Button } from "@/components/ui/button"

const plans = [
  {
    name: "Бесплатный",
    subtitle: "Попробовать",
    price: "0",
    features: [
      "1 компания",
      "До 2 AI-резюме",
      "До 10 RAG-вопросов",
      "«Для вас» 10 тендеров",
    ],
  },
  {
    name: "Standard",
    subtitle: "Для специалиста",
    price: "2 990",
    features: [
      "1 компания",
      "До 60 AI-резюме",
      "До 120 RAG-вопросов",
      "«Для вас» без ограничений",
    ],
  },
  {
    name: "Premium",
    subtitle: "Для команды",
    price: "6 990",
    features: [
      "До 10 компаний",
      "До 500 AI-резюме",
      "До 1 000 RAG-вопросов",
      "«Для вас» без ограничений",
    ],
  },
  {
    name: "Enterprise",
    subtitle: "Для крупных команд",
    price: "Договорная",
    features: [
      "Условия договорные",
      "Персональный менеджер",
      "API доступ",
    ],
  },
]

export function Pricing() {
  return (
    <section id="pricing" className="bg-[#F3F4F6] py-16 sm:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight text-[#111827] sm:text-4xl">
            Прозрачные тарифы
          </h2>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className="border-2 border-[#D1D5DB] bg-white p-8"
            >

              <div className="text-center">
                <h3 className="text-lg font-semibold text-[#111827]">{plan.name}</h3>
                <p className="mt-1 text-sm text-[#6B7280]">{plan.subtitle}</p>
                <div className="mt-6">
                  {plan.price === "Договорная" ? (
                    <span className="text-3xl font-bold text-[#111827]">{plan.price}</span>
                  ) : plan.price === "0" ? (
                    <span className="text-4xl font-bold text-[#111827]">Бесплатно</span>
                  ) : (
                    <>
                      <span className="text-4xl font-bold text-[#111827]">{plan.price}</span>
                      <span className="ml-1 text-[#6B7280]">₽/мес</span>
                    </>
                  )}
                </div>
              </div>

              <ul className="mt-8 space-y-4">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-3">
                    <Check className="h-5 w-5 flex-shrink-0 text-[#111827]" />
                    <span className="text-sm text-[#374151]">{feature}</span>
                  </li>
                ))}
              </ul>

              <div className="mt-8">
                <Button
                  variant="outline"
                  className="w-full rounded-none border-[#D1D5DB] bg-white text-[#374151] hover:bg-[#F3F4F6]"
                >
                  {plan.price === "Договорная" ? "Связаться" : "Начать"}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
