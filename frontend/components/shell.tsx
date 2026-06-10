"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import Link from "next/link"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { clearTokens, isAuthenticated } from "@/lib/auth"
import { profileApi } from "@/lib/api"
import { FileText, Columns3, Settings, LogOut, Send, Mail, CreditCard, Menu, X } from "lucide-react"

const NAV = [
  { href: "/tenders", icon: FileText, label: "Тендеры" },
  { href: "/pipeline", icon: Columns3, label: "Мои тендеры" },
  { href: "/profile", icon: Settings, label: "Профиль" },
]

function SidebarContent({ onNavigate, guest }: { onNavigate?: () => void; guest?: boolean }) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const searchStr = searchParams.toString()
  const router = useRouter()
  const qc = useQueryClient()
  const { data: me } = useQuery<{ email: string }>({
    queryKey: ["me"],
    queryFn: () => profileApi.getMe(),
    staleTime: 300_000,
    enabled: !guest,
  })

  return (
    <>
      {/* Logo */}
      <div className="h-16 flex items-center px-5 border-b border-gray-200 shrink-0">
        <Link href="/" className="flex items-center gap-3" onClick={onNavigate}>
          <img src="/logo.svg" width={28} height={28} alt="TendeRoll" />
          <span className="text-lg font-bold text-[#111827]">TendeRoll</span>
        </Link>
      </div>

      {/* Guest login button at top */}
      {guest && (
        <div className="px-3 pt-3 pb-1 shrink-0">
          <Link
            href={pathname === "/" || pathname.startsWith("/login") ? "/login" : `/login?redirect=${encodeURIComponent(pathname + (searchStr ? `?${searchStr}` : ""))}`}
            onClick={onNavigate}
            className="flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-white bg-[#111827] hover:bg-black transition-colors rounded w-full"
          >
            Войти / Зарегистрироваться
          </Link>
        </div>
      )}

      {/* Nav items */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = pathname.startsWith(href)
          const guestBlocked = guest && href !== "/tenders"
          return (
            <Link
              key={href}
              href={guestBlocked ? "/login" : href}
              onClick={onNavigate}
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

      {/* Plan link */}
      {!guest && <nav className="px-3 py-1 shrink-0 border-t border-gray-200">
        <Link
          href="/plan"
          onClick={onNavigate}
          className={`
            flex items-center gap-3 px-4 py-3 text-base transition-all duration-200 border-l-[3px]
            ${pathname.startsWith("/plan")
              ? "bg-gray-50 text-[#111827] font-medium border-l-[#111827]"
              : "text-gray-500 hover:text-[#111827] hover:bg-gray-50 border-l-transparent"
            }
          `}
        >
          <CreditCard className="w-5 h-5 shrink-0" />
          Мой тариф
        </Link>
      </nav>}

      {/* Support block */}
      <div className="px-3 pb-2 shrink-0">
        <div className="border-t border-gray-200 pt-3 space-y-0.5">
          <p className="pl-[19px] text-sm font-medium text-gray-400 uppercase tracking-wide mb-1.5">Поддержка</p>
          <a
            href="https://t.me/tenderoll_support"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 pl-[19px] pr-4 py-2 text-[15px] text-gray-500 hover:text-[#111827] hover:bg-gray-50 transition-colors"
          >
            <Send className="w-5 h-5 shrink-0" />
            <span>Telegram</span>
          </a>
          <a
            href="mailto:support@tenderoll.ru"
            className="flex items-center gap-3 pl-[19px] pr-4 py-2 text-[15px] text-gray-500 hover:text-[#111827] hover:bg-gray-50 transition-colors"
          >
            <Mail className="w-5 h-5 shrink-0" />
            <span>Email</span>
          </a>
        </div>
      </div>

      {/* Bottom: user + logout / guest login */}
      <div className="px-3 py-3 border-t border-gray-200 shrink-0">
        {!guest && (
          <>
            {me?.email && (
              <p className="pl-[19px] pr-4 pb-2 text-sm text-gray-400 truncate">{me.email}</p>
            )}
            <button
              onClick={() => { clearTokens(); qc.clear(); router.push("/login") }}
              className="flex items-center gap-3 pl-[19px] pr-4 py-3 text-base text-gray-500 hover:text-[#111827] hover:bg-gray-50 transition-all duration-200 w-full"
            >
              <LogOut className="w-5 h-5" />
              Выйти
            </button>
          </>
        )}
      </div>
    </>
  )
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [mounted, setMounted] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    setSidebarOpen(false)
  }, [pathname])

  if (!mounted || pathname === "/" || pathname === "/login") {
    return <>{children}</>
  }

  if (!isAuthenticated()) {
    if (pathname?.startsWith("/tenders")) {
      return (
        <div className="flex min-h-screen">
          {/* Mobile header */}
          <div className="fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 flex items-center px-4 gap-3 z-40 md:hidden">
            <button
              onClick={() => setSidebarOpen(true)}
              className="p-1 text-gray-500 hover:text-[#111827] transition-colors"
            >
              <Menu className="w-6 h-6" />
            </button>
            <Link href="/" className="flex items-center gap-2">
              <img src="/logo.svg" width={24} height={24} alt="TendeRoll" />
              <span className="text-base font-bold text-[#111827]">TendeRoll</span>
            </Link>
          </div>

          {/* Mobile sidebar overlay */}
          {sidebarOpen && (
            <div className="fixed inset-0 z-50 md:hidden">
              <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
              <aside className="relative w-[280px] bg-white h-full flex flex-col overflow-y-auto">
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="absolute top-4 right-3 p-1 text-gray-400 hover:text-gray-600 z-10"
                >
                  <X className="w-5 h-5" />
                </button>
                <SidebarContent guest onNavigate={() => setSidebarOpen(false)} />
              </aside>
            </div>
          )}

          {/* Desktop sidebar */}
          <aside className="hidden md:flex w-[260px] shrink-0 border-r border-gray-200 bg-white flex-col h-screen sticky top-0">
            <SidebarContent guest />
          </aside>

          {/* Content */}
          <div className="flex-1 min-w-0 overflow-auto pt-14 md:pt-0">
            {children}
          </div>
        </div>
      )
    }
    return <>{children}</>
  }

  return (
    <div className="flex min-h-screen">
      {/* Mobile header */}
      <div className="fixed top-0 left-0 right-0 h-14 bg-white border-b border-gray-200 flex items-center px-4 gap-3 z-40 md:hidden">
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-1 text-gray-500 hover:text-[#111827] transition-colors"
        >
          <Menu className="w-6 h-6" />
        </button>
        <Link href="/" className="flex items-center gap-2">
          <img src="/logo.svg" width={24} height={24} alt="TendeRoll" />
          <span className="text-base font-bold text-[#111827]">TendeRoll</span>
        </Link>
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
          <aside className="relative w-[280px] bg-white h-full flex flex-col overflow-y-auto">
            <button
              onClick={() => setSidebarOpen(false)}
              className="absolute top-4 right-3 p-1 text-gray-400 hover:text-gray-600 z-10"
            >
              <X className="w-5 h-5" />
            </button>
            <SidebarContent onNavigate={() => setSidebarOpen(false)} />
          </aside>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-[260px] shrink-0 border-r border-gray-200 bg-white flex-col h-screen sticky top-0">
        <SidebarContent />
      </aside>

      {/* Content */}
      <div className="flex-1 min-w-0 overflow-auto pt-14 md:pt-0">
        {children}
      </div>
    </div>
  )
}
