"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { clearTokens, isAuthenticated } from "@/lib/auth"
import { Button } from "@/components/ui/button"
import { Search, Building2, LogOut } from "lucide-react"

export function Nav() {
  const pathname = usePathname()
  const router = useRouter()

  function handleLogout() {
    clearTokens()
    router.push("/login")
  }

  if (!isAuthenticated()) return null

  return (
    <nav className="border-b bg-white sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
        <Link href="/tenders" className="font-semibold text-lg">
          Tender Pilot
        </Link>
        <div className="flex items-center gap-2">
          <Link href="/tenders">
            <Button variant={pathname.startsWith("/tenders") ? "secondary" : "ghost"} size="sm">
              <Search className="w-4 h-4 mr-1" /> Тендеры
            </Button>
          </Link>
          <Link href="/profile">
            <Button variant={pathname === "/profile" ? "secondary" : "ghost"} size="sm">
              <Building2 className="w-4 h-4 mr-1" /> Профиль
            </Button>
          </Link>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            <LogOut className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </nav>
  )
}
