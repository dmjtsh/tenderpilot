import type { MetadataRoute } from "next"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api/v1"
const SITE = "https://tenderoll.ru"
const PER_SITEMAP = 45000

type SitemapEntry = { id: number; updated_at: string | null }

async function fetchSitemapData(): Promise<SitemapEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/tenders/sitemap/`, { next: { revalidate: 86400 } })
    if (!res.ok) return []
    const json = await res.json()
    return json.results ?? []
  } catch {
    return []
  }
}

export async function generateSitemaps() {
  const data = await fetchSitemapData()
  const count = Math.max(1, Math.ceil(data.length / PER_SITEMAP))
  return Array.from({ length: count }, (_, i) => ({ id: i }))
}

export default async function sitemap({ id }: { id: number }): Promise<MetadataRoute.Sitemap> {
  const data = await fetchSitemapData()
  const slice = data.slice(id * PER_SITEMAP, (id + 1) * PER_SITEMAP)

  const staticPages: MetadataRoute.Sitemap =
    id === 0
      ? [
          { url: SITE, lastModified: new Date(), changeFrequency: "weekly", priority: 1.0 },
          { url: `${SITE}/tenders`, lastModified: new Date(), changeFrequency: "hourly", priority: 0.9 },
          { url: `${SITE}/privacy`, changeFrequency: "yearly", priority: 0.2 },
          { url: `${SITE}/oferta`, changeFrequency: "yearly", priority: 0.2 },
        ]
      : []

  const tenderPages: MetadataRoute.Sitemap = slice.map((t) => ({
    url: `${SITE}/tenders/${t.id}`,
    lastModified: t.updated_at ? new Date(t.updated_at) : new Date(),
    changeFrequency: "daily" as const,
    priority: 0.7,
  }))

  return [...staticPages, ...tenderPages]
}
