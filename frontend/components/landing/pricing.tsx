import { Check } from "lucide-react"
import { Button } from "@/components/ui/button"

const plans = [
  {
    name: "Solo",
    subtitle: "Для специалиста",
    price: "3 000",
    popular: false,
    features: [
      "1 пользователь",
      "2 направления",
      "ИИ резюме",
      "Telegram алерты",
    ],
  },
  {
    name: "Team",
    subtitle: "Для команды",
    price: "9 000",
    popular: true,
    features: [
      "До 5 пользователей",
      "До 5 направлений",
      "Всё из Solo",
      "Командная работа",
      "Kanban доска",
    ],
  },
  {
    name: "Enterprise",
    subtitle: "Для крупных команд",
    price: "По запросу",
    popular: false,
    features: [
      "Безлимит пользователей",
      "API доступ",
      "White-label",
      "Персональный менеджер",
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

        <div className="mt-12 grid grid-cols-1 gap-8 lg:grid-cols-3">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`relative border-2 bg-white p-8 ${
                plan.popular
                  ? "border-[#111827] shadow-lg"
                  : "border-[#D1D5DB]"
              }`}
            >
              {plan.popular && (
                <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                  <span className="bg-[#111827] px-4 py-1 text-sm font-medium text-white">
                    Популярный
                  </span>
                </div>
              )}

              <div className="text-center">
                <h3 className="text-lg font-semibold text-[#111827]">{plan.name}</h3>
                <p className="mt-1 text-sm text-[#6B7280]">{plan.subtitle}</p>
                <div className="mt-6">
                  {plan.price === "По запросу" ? (
                    <span className="text-3xl font-bold text-[#111827]">{plan.price}</span>
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
                {plan.popular ? (
                  <Button className="w-full rounded-none bg-[#111827] text-white hover:bg-[#1f2937]">
                    Начать
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    className="w-full rounded-none border-[#D1D5DB] bg-white text-[#374151] hover:bg-[#F3F4F6]"
                  >
                    {plan.price === "По запросу" ? "Связаться" : "Начать"}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
