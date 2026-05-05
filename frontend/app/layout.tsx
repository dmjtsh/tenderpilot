import type { Metadata } from "next"
import { Inter, Playfair_Display } from "next/font/google"
import "./globals.css"
import { Providers } from "./providers"
import { Shell } from "@/components/shell"

const inter = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-sans" })
const playfair = Playfair_Display({ subsets: ["latin", "cyrillic"], variable: "--font-serif", style: ["normal", "italic"] })

export const metadata: Metadata = {
  title: "Tender Pilot",
  description: "AI-поиск тендеров",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={`${inter.variable} ${playfair.variable}`}>
      <body className="font-sans antialiased">
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  )
}
