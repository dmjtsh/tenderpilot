export type Interval = "monthly" | "halfyearly" | "yearly"

export interface Plan {
  key: string
  name: string
  subtitle: string
  monthly: number
  halfyearly: number
  yearly: number
  features: string[]
}

export const plans: Plan[] = [
  {
    key: "free",
    name: "Бесплатный",
    subtitle: "Попробовать",
    monthly: 0,
    halfyearly: 0,
    yearly: 0,
    features: [
      "1 компания",
      "До 2 AI-резюме",
      "До 10 RAG-вопросов",
      "Для вас: 10 тендеров",
    ],
  },
  {
    key: "standard",
    name: "Standard",
    subtitle: "Для специалиста",
    monthly: 2990,
    halfyearly: 14950,
    yearly: 26910,
    features: [
      "1 компания",
      "До 60 AI-резюме",
      "До 120 RAG-вопросов",
      "Для вас: без ограничений",
      "Доступ к коммерческим тендерам",
    ],
  },
  {
    key: "premium",
    name: "Premium",
    subtitle: "Для команды",
    monthly: 6990,
    halfyearly: 34950,
    yearly: 62910,
    features: [
      "До 10 компаний",
      "До 500 AI-резюме",
      "До 1 000 RAG-вопросов",
      "Для вас: без ограничений",
      "Доступ к коммерческим тендерам",
    ],
  },
  {
    key: "enterprise",
    name: "Enterprise",
    subtitle: "Для крупных команд",
    monthly: -1,
    halfyearly: -1,
    yearly: -1,
    features: [
      "Условия договорные",
      "Персональный менеджер",
      "API доступ",
      "Доступ к коммерческим тендерам",
    ],
  },
]

export const INTERVAL_MONTHS: Record<Interval, number> = {
  monthly: 1,
  halfyearly: 6,
  yearly: 12,
}

export const INTERVAL_LABEL: Record<Interval, string> = {
  monthly: "мес",
  halfyearly: "полгода",
  yearly: "год",
}

export function formatPrice(price: number) {
  return price.toLocaleString("ru-RU")
}
