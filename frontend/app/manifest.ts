import type { MetadataRoute } from "next"

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "TendeRoll",
    short_name: "TendeRoll",
    description: "ИИ-платформа для поиска и анализа государственных закупок",
    start_url: "/",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#111827",
  }
}
