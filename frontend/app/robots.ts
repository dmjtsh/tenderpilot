import type { MetadataRoute } from "next"

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/login", "/tenders", "/profile", "/pipeline", "/api/"],
      },
    ],
    sitemap: "https://pilot-tender.ru/sitemap.xml",
    host: "https://pilot-tender.ru",
  }
}
