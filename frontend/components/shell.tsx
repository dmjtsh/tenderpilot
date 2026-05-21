"use client"

import { useEffect, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import Link from "next/link"
import { clearTokens, isAuthenticated } from "@/lib/auth"
import Image from "next/image"
import { FileText, Columns3, Settings, LogOut, Send, Mail, HeadphonesIcon, Globe } from "lucide-react"

const NAV = [
  { href: "/tenders", icon: FileText, label: "Тендеры" },
  { href: "/pipeline", icon: Columns3, label: "Мои тендеры" },
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
          <Image src="/new_logo.jpg" width={28} height={28} className="rounded-xl" alt="ТендерПилот" />
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

      {/* Support block */}
      <div className="px-3 pb-2 shrink-0">
        <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 space-y-1">
          <div className="flex items-center gap-2 px-1 pb-1">
            <HeadphonesIcon className="w-4 h-4 text-violet-600 shrink-0" />
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Тех. поддержка</span>
          </div>
          <a
            href="https://t.me/tender_pilot"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-violet-700 hover:bg-violet-50 transition-all duration-150 group"
          >
            <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-[#2AABEE]/10 group-hover:bg-[#2AABEE]/20 transition-colors">
              <Send className="w-3.5 h-3.5 text-[#2AABEE]" />
            </span>
            <div className="min-w-0">
              <div className="font-medium leading-tight">Telegram</div>
              <div className="text-xs text-gray-400">@tender_pilot</div>
            </div>
          </a>
          <a
            href="#"
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-violet-700 hover:bg-violet-50 transition-all duration-150 group cursor-not-allowed opacity-60"
          >
            <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-orange-100 group-hover:bg-orange-200 transition-colors">
              <Globe className="w-3.5 h-3.5 text-orange-500" />
            </span>
            <div className="min-w-0">
              <div className="font-medium leading-tight">Max</div>
              <div className="text-xs text-gray-400">скоро</div>
            </div>
          </a>
          <a
            href="mailto:support@tenderpilot.ru"
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-600 hover:text-violet-700 hover:bg-violet-50 transition-all duration-150 group"
          >
            <span className="flex items-center justify-center w-7 h-7 rounded-lg bg-violet-100 group-hover:bg-violet-200 transition-colors">
              <Mail className="w-3.5 h-3.5 text-violet-600" />
            </span>
            <div className="min-w-0">
              <div className="font-medium leading-tight">Email</div>
              <div className="text-xs text-gray-400">support@tenderpilot.ru</div>
            </div>
          </a>
        </div>
      </div>

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
