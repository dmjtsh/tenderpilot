import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Тендеры: 44-ФЗ, 223-ФЗ и коммерческие закупки",
  description: "TendeRoll (Тендерол) — поиск тендеров по 44-ФЗ, 223-ФЗ и коммерческих закупок. AI-анализ, мониторинг, персональный подбор.",
  keywords: ["TendeRoll", "тендерол", "tenderoll", "тендеролл", "тендеры", "госзакупки", "44-ФЗ", "223-ФЗ", "поиск тендеров"],
  alternates: { canonical: "/tenders" },
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
