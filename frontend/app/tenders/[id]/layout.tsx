import type { Metadata } from "next"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api/v1"

interface TenderData {
  id: number
  number: string
  title: string
  nmck: number | null
  region: string
  law_type: string
  procedure_type?: string
  status: string
  published_at: string | null
  deadline_at: string | null
  updated_at: string | null
  customer?: { name: string; full_name: string; inn: string } | null
  is_restricted?: boolean
}

const LAW_LABEL: Record<string, string> = {
  "44-ФЗ": "44-ФЗ",
  "223-ФЗ": "223-ФЗ",
  "615-ПП": "615-ПП",
  b2b: "Коммерческий тендер",
}

const PROCEDURE_LABEL: Record<string, string> = {
  auction: "Электронный аукцион",
  contest: "Конкурс",
  request_quotations: "Запрос котировок",
  request_proposals: "Запрос предложений",
  single_source: "Единственный поставщик",
  other: "Иной способ",
}

function fmtPrice(n: number | null): string {
  if (n == null) return ""
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n) + " \u20BD"
}

function fmtDate(s: string | null): string {
  if (!s) return ""
  return new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
}

async function fetchTender(id: string): Promise<TenderData | null> {
  try {
    const res = await fetch(`${API_BASE}/tenders/${id}/`, { next: { revalidate: 3600 } })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  const tender = await fetchTender(id)
  if (!tender) return { title: "Тендер" }

  const lawLabel = LAW_LABEL[tender.law_type] ?? tender.law_type
  const price = fmtPrice(tender.nmck)
  const procedure = tender.procedure_type ? PROCEDURE_LABEL[tender.procedure_type] ?? "" : ""
  const deadline = fmtDate(tender.deadline_at)
  const customerName = tender.is_restricted ? "" : (tender.customer?.name ?? "")

  const descParts = [
    `${lawLabel}${tender.number ? ` №${tender.number}` : ""}`,
    price ? `НМЦК ${price}` : "",
    tender.region,
    procedure,
    deadline ? `Дедлайн: ${deadline}` : "",
    customerName ? `Заказчик: ${customerName}` : "",
  ].filter(Boolean)
  const description = descParts.join(". ") + "."

  return {
    title: tender.title,
    description,
    alternates: { canonical: `/tenders/${id}` },
    openGraph: {
      title: tender.title,
      description,
      url: `/tenders/${id}`,
      type: "article",
      locale: "ru_RU",
      siteName: "TendeRoll",
      images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: tender.title }],
    },
    twitter: {
      card: "summary_large_image",
      title: tender.title,
      description,
      images: ["/opengraph-image"],
    },
  }
}

function buildJsonLd(tender: TenderData) {
  const url = `https://tenderoll.ru/tenders/${tender.id}`
  const truncTitle = tender.title.length > 60 ? tender.title.slice(0, 57) + "..." : tender.title

  const breadcrumb = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "TendeRoll", item: "https://tenderoll.ru" },
      { "@type": "ListItem", position: 2, name: "Тендеры", item: "https://tenderoll.ru/tenders" },
      { "@type": "ListItem", position: 3, name: truncTitle, item: url },
    ],
  }

  const lawLabel = LAW_LABEL[tender.law_type] ?? tender.law_type
  const descParts = [lawLabel, tender.region, fmtPrice(tender.nmck)].filter(Boolean)

  const product: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: tender.title,
    description: descParts.join(". "),
    url,
  }

  if (tender.nmck != null) {
    product.offers = {
      "@type": "Offer",
      price: tender.nmck,
      priceCurrency: "RUB",
      availability: tender.status === "active" ? "https://schema.org/InStock" : "https://schema.org/Discontinued",
      ...(tender.deadline_at ? { validThrough: tender.deadline_at } : {}),
    }
  }

  if (!tender.is_restricted && tender.customer?.name) {
    product.brand = { "@type": "Organization", name: tender.customer.name }
  }

  return [breadcrumb, product]
}

export default async function Layout({
  children,
  params,
}: {
  children: React.ReactNode
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const tender = await fetchTender(id)

  if (!tender) return <>{children}</>

  const jsonLd = buildJsonLd(tender)
  const lawLabel = LAW_LABEL[tender.law_type] ?? tender.law_type
  const procedure = tender.procedure_type ? PROCEDURE_LABEL[tender.procedure_type] ?? "" : ""
  const customerName = !tender.is_restricted ? (tender.customer?.full_name || tender.customer?.name || "") : ""

  return (
    <>
      {jsonLd.map((schema, i) => (
        <script
          key={i}
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
        />
      ))}
      <div className="sr-only" aria-hidden="true">
        <h1>{tender.title}</h1>
        {tender.number && <p>Номер: {tender.number}</p>}
        <p>Тип: {lawLabel}</p>
        {tender.nmck != null && <p>НМЦК: {fmtPrice(tender.nmck)}</p>}
        {tender.region && <p>Регион: {tender.region}</p>}
        {procedure && <p>Процедура: {procedure}</p>}
        {tender.deadline_at && <p>Дедлайн: {fmtDate(tender.deadline_at)}</p>}
        {customerName && <p>Заказчик: {customerName}</p>}
      </div>
      {children}
    </>
  )
}
