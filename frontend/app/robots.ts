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
    sitemap: "https://tenderoll.ru/sitemap.xml",
    host: "https://tenderoll.ru",
  }
}
