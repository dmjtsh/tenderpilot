"use client"

import { useState, useEffect, useRef } from "react"
import { X, ChevronsUpDown, Check } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { okvedApi } from "@/lib/api"

interface OkvedOption {
  code: string
  name: string
}

interface OkvedComboboxProps {
  value: string[]
  onChange: (codes: string[]) => void
}

const POPULAR: OkvedOption[] = [
  { code: "43.91", name: "Производство кровельных работ" },
  { code: "41.20", name: "Строительство жилых и нежилых зданий" },
  { code: "42.11", name: "Строительство автомобильных дорог и автострад" },
  { code: "42.21", name: "Строительство водопроводных и канализационных сетей" },
  { code: "43.99", name: "Работы строительные специализированные прочие" },
  { code: "81.30", name: "Деятельность по благоустройству ландшафта" },
  { code: "43.31", name: "Производство штукатурных работ" },
  { code: "43.32", name: "Работы по устройству покрытий полов и облицовке стен" },
  { code: "43.33", name: "Работы по устройству покрытий полов и стен" },
  { code: "43.21", name: "Производство электромонтажных работ" },
  { code: "43.22", name: "Производство санитарно-технических работ" },
  { code: "42.91", name: "Строительство гидротехнических сооружений" },
  { code: "43.12", name: "Подготовка строительной площадки" },
  { code: "43.13", name: "Разведочное бурение" },
  { code: "41.10", name: "Разработка строительных проектов" },
  { code: "42.22", name: "Строительство коммунальных объектов" },
  { code: "43.11", name: "Разборка и снос зданий" },
  { code: "43.34", name: "Производство малярных и стекольных работ" },
  { code: "81.10", name: "Деятельность по комплексному обслуживанию помещений" },
  { code: "42.99", name: "Строительство прочих объектов" },
]

export function OkvedCombobox({ value, onChange }: OkvedComboboxProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onClickOutside)
    return () => document.removeEventListener("mousedown", onClickOutside)
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
    else setQuery("")
  }, [open])

  const { data: searchResults = [] } = useQuery<OkvedOption[]>({
    queryKey: ["okved", query],
    queryFn: () => okvedApi.search(query),
    enabled: query.length > 0,
    staleTime: 60_000,
  })

  const options: OkvedOption[] = query.length === 0 ? POPULAR : searchResults

  function toggle(code: string, name: string) {
    if (value.includes(code)) {
      onChange(value.filter((c) => c !== code))
    } else {
      onChange([...value, code])
    }
  }

  return (
    <div ref={ref} className="space-y-1.5">
      {/* Selected tags */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((code) => (
            <span
              key={code}
              className="inline-flex items-center gap-1 h-5 px-2 text-[11px] rounded-md bg-primary/15 text-primary border border-primary/25 font-mono"
            >
              {code}
              <button
                type="button"
                onClick={() => onChange(value.filter((c) => c !== code))}
                className="text-primary/60 hover:text-primary transition-colors"
              >
                <X className="w-2.5 h-2.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full h-8 flex items-center justify-between gap-2 rounded-md bg-secondary border border-border px-3 text-sm text-left hover:border-border/80 transition-colors"
      >
        <span className="text-muted-foreground/60 text-sm">
          {value.length === 0 ? "Поиск по коду или названию..." : `${value.length} выбрано`}
        </span>
        <ChevronsUpDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="relative z-50">
          <div className="absolute top-0 left-0 right-0 rounded-md border border-border bg-popover shadow-lg overflow-hidden">
            {/* Search input */}
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
              <input
                ref={inputRef}
                className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
                placeholder="Код или название..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              {query && (
                <button type="button" onClick={() => setQuery("")} className="text-muted-foreground/50 hover:text-muted-foreground">
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* List */}
            <div className="max-h-64 overflow-y-auto">
              {query.length === 0 && (
                <p className="px-3 pt-2 pb-1 text-[10px] text-muted-foreground/50 uppercase tracking-wide">
                  Популярные
                </p>
              )}
              {options.length === 0 ? (
                <p className="px-3 py-3 text-xs text-muted-foreground text-center">Ничего не найдено</p>
              ) : (
                options.map((opt) => {
                  const selected = value.includes(opt.code)
                  return (
                    <button
                      key={opt.code}
                      type="button"
                      onClick={() => toggle(opt.code, opt.name)}
                      className={`w-full flex items-start gap-2.5 px-3 py-2 text-left hover:bg-secondary/60 transition-colors ${selected ? "bg-primary/5" : ""}`}
                    >
                      <Check className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${selected ? "text-primary opacity-100" : "opacity-0"}`} />
                      <div className="min-w-0">
                        <p className="font-mono text-xs font-semibold text-foreground">{opt.code}</p>
                        <p className="text-[11px] text-muted-foreground leading-tight mt-0.5 truncate">{opt.name}</p>
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
