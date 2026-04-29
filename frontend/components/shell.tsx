"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import Link from "next/link"
import { clearTokens, isAuthenticated } from "@/lib/auth"
import { Zap, FileText, Settings, LogOut } from "lucide-react"

const NAV = [
  { href: "/tenders", icon: FileText, label: "Тендеры" },
  { href: "/profile", icon: Settings, label: "Профиль" },
]

function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()

  return (
    <aside className="w-[220px] shrink-0 border-r border-border flex flex-col h-screen sticky top-0">
      {/* Logo */}
      <div className="h-[52px] flex items-center px-4 border-b border-border shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-6 h-6 rounded-md bg-primary/90 flex items-center justify-center">
            <Zap className="w-3.5 h-3.5 text-white" strokeWidth={2.5} />
          </div>
          <span className="text-sm font-semibold tracking-tight">Tender Pilot</span>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = pathname.startsWith(href)
          return (
            <Link
              key={href}
              href={href}
              className={`
                flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm transition-colors
                ${active
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-secondary/60"
                }
              `}
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </Link>
          )
        })}
      </nav>

      {/* Bottom: logout */}
      <div className="px-2 py-2 border-t border-border shrink-0">
        <button
          onClick={() => { clearTokens(); router.push("/login") }}
          className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-secondary/60 transition-colors w-full"
        >
          <LogOut className="w-4 h-4" />
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
  if (!mounted || pathname === "/login" || !isAuthenticated()) {
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
