"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import Link from "next/link"
import { clearTokens, isAuthenticated } from "@/lib/auth"
import Image from "next/image"
import { FileText, Settings, LogOut } from "lucide-react"

const NAV = [
  { href: "/tenders", icon: FileText, label: "Тендеры" },
  { href: "/profile", icon: Settings, label: "Профиль" },
]

function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()

  return (
    <aside className="w-[260px] shrink-0 border-r border-gray-200 bg-white flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-gray-200 shrink-0">
        <Link href="/" className="flex items-center gap-3">
          <Image src="/logo.png" width={28} height={28} className="rounded-xl" alt="ТендерПилот" />
          <span className="text-lg font-bold text-[#111827]">ТендерПилот</span>
        </Link>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`
                flex items-center gap-3 px-4 py-3 text-base transition-all duration-200 border-l-[3px]
                ${active
                  ? "bg-gray-50 text-[#111827] font-medium border-l-[#111827]"
                  : "text-gray-500 hover:text-[#111827] hover:bg-gray-50 border-l-transparent"
                }
              `}
            >
              <Icon className="w-5 h-5 shrink-0" />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Bottom: logout */}
      <div className="px-3 py-3 border-t border-gray-200 shrink-0">
        <button
          onClick={() => { clearTokens(); router.push("/login") }}
          className="flex items-center gap-3 px-4 py-3 text-base text-gray-500 hover:text-[#111827] hover:bg-gray-50 transition-all duration-200 w-full"
        >
          <LogOut className="w-5 h-5" />
          Выйти
        </button>
      </div>
    </aside>
  )
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  // До гидрации рендерим без сайдбара — совпадает с SSR-выводом
  if (!mounted || pathname === "/" || pathname === "/login" || !isAuthenticated()) {
    return <>{children}</>
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 min-w-0 overflow-auto">
        {children}
      </div>
    </div>
  )
}
