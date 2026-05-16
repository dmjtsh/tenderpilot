"use client"

import { useRef, useState, useEffect, type ReactNode } from "react"
import { ChevronDown } from "lucide-react"

interface Props {
  label: string
  activeCount?: number
  children: ReactNode
  className?: string
  wide?: boolean
}

export function FilterDropdown({ label, activeCount, children, className, wide }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [open])

  const active = (activeCount ?? 0) > 0

  return (
    <div ref={ref} className={`relative ${className ?? ""}`}>
      <button
        onClick={() => setOpen(!open)}
        className={`inline-flex items-center gap-1.5 h-8 px-3 text-sm border rounded-md transition-colors whitespace-nowrap ${
          active
            ? "bg-violet-50 border-violet-200 text-violet-700"
            : "border-gray-200 text-gray-600 hover:border-gray-300 hover:text-gray-900"
        }`}
      >
        {label}
        {active ? <span className="text-xs font-medium ml-0.5">({activeCount})</span> : null}
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className={`absolute top-full left-0 mt-1.5 z-50 bg-white border border-gray-200 rounded-lg shadow-lg ${wide ? "w-[420px]" : "min-w-[220px]"}`}>
          {children}
        </div>
      )}
    </div>
  )
}
