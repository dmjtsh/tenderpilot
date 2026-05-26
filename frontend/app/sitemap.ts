import type { MetadataRoute } from "next"

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: "https://tenderoll.ru",
      lastModified: "2026-05-26",
      changeFrequency: "weekly",
      priority: 1.0,
    },
  ]
}
