import type { Metadata } from "next"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api/v1"

function fmtPrice(n: number | null): string {
  if (n == null) return ""
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) + " \u20BD"
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  try {
    const res = await fetch(`${API_BASE}/tenders/${id}/`, { next: { revalidate: 3600 } })
    if (!res.ok) return { title: "Тендер" }
    const tender = await res.json()
    const lawLabel = tender.law_type === "b2b" ? "Коммерческий тендер" : tender.law_type
    const price = fmtPrice(tender.nmck)
    const description = [lawLabel, price, tender.region].filter(Boolean).join(". ")

    return {
      title: tender.title,
      description,
      openGraph: {
        title: tender.title,
        description,
      },
    }
  } catch {
    return { title: "Тендер" }
  }
}

export default function Layout({ children }: { children: React.ReactNode }) {
  return children
}
