"use client"

import { useEffect, useState } from "react"
import { Menu, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { isAuthenticated } from "@/lib/auth"
import Link from "next/link"

const navLinks = [
  { label: "Решение", href: "#solution" },
  { label: "Как работает", href: "#how-it-works" },
  { label: "Тарифы", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
]

export function Navbar() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [authed, setAuthed] = useState(false)

  useEffect(() => {
    setAuthed(isAuthenticated())
  }, [])

  return (
    <header className="sticky top-0 z-50 w-full border-b border-[#D1D5DB] bg-white">
      <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <img src="/logo.svg" width={28} height={28} alt="TendeRoll" />
          <span className="text-lg font-bold text-[#111827]">TendeRoll</span>
        </Link>

        {/* Desktop Navigation */}
        <div className="hidden items-center gap-8 sm:flex">
          {navLinks.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm font-medium text-[#374151] transition-colors hover:text-[#111827]"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Desktop CTA */}
        <div className="hidden items-center gap-4 sm:flex">
          {authed ? (
            <Link href="/tenders">
              <Button className="rounded-none bg-[#111827] text-white hover:bg-[#1f2937] btn-hover-lift">
                Личный кабинет
              </Button>
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="text-sm font-medium text-[#374151] transition-colors hover:text-[#111827]"
              >
                Войти
              </Link>
              <Link href="/login">
                <Button className="rounded-none bg-[#111827] text-white hover:bg-[#1f2937] btn-hover-lift">
                  Попробовать бесплатно
                </Button>
              </Link>
            </>
          )}
        </div>

        {/* Mobile Menu Button */}
        <button
          className="sm:hidden"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle menu"
        >
          {mobileMenuOpen ? (
            <X className="h-6 w-6 text-[#111827]" />
          ) : (
            <Menu className="h-6 w-6 text-[#111827]" />
          )}
        </button>
      </nav>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="border-t border-[#D1D5DB] bg-white sm:hidden">
          <div className="space-y-1 px-4 py-4">
            {navLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="block py-2 text-sm font-medium text-[#374151] transition-colors hover:text-[#111827]"
                onClick={() => setMobileMenuOpen(false)}
              >
                {link.label}
              </a>
            ))}
            <hr className="my-4 border-[#D1D5DB]" />
            {authed ? (
              <Link href="/tenders" onClick={() => setMobileMenuOpen(false)}>
                <Button className="w-full rounded-none bg-[#111827] text-white hover:bg-[#1f2937]">
                  Личный кабинет
                </Button>
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="block py-2 text-sm font-medium text-[#374151] transition-colors hover:text-[#111827]"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Войти
                </Link>
                <Link href="/login" onClick={() => setMobileMenuOpen(false)}>
                  <Button className="mt-2 w-full rounded-none bg-[#111827] text-white hover:bg-[#1f2937]">
                    Попробовать бесплатно
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  )
}
