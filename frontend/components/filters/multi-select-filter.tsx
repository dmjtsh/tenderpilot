"use client"

import { useState, useRef, useEffect } from "react"
import { Search, Check } from "lucide-react"

interface Option {
  value: string
  label: string
}

interface Props {
  options: Option[]
  selected: string[]
  onChange: (next: string[]) => void
  searchable?: boolean
  searchPlaceholder?: string
  loading?: boolean
  onSearch?: (q: string) => void
}

export function MultiSelectFilter({
  options,
  selected,
  onChange,
  searchable,
  searchPlaceholder = "Поиск...",
  loading,
  onSearch,
}: Props) {
  const [query, setQuery] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (searchable) inputRef.current?.focus()
  }, [searchable])

  const handleQuery = (q: string) => {
    setQuery(q)
    onSearch?.(q)
  }

  const filtered = onSearch
    ? options
    : options.filter(
        (o) =>
          o.label.toLowerCase().includes(query.toLowerCase()) ||
          o.value.toLowerCase().includes(query.toLowerCase())
      )

  const toggle = (val: string) => {
    onChange(
      selected.includes(val)
        ? selected.filter((v) => v !== val)
        : [...selected, val]
    )
  }

  return (
    <div className="py-1">
      {searchable && (
        <div className="px-2 pb-1.5 pt-1">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => handleQuery(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full h-8 pl-8 pr-3 text-sm border border-gray-200 rounded-md bg-gray-50 text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
            />
          </div>
        </div>
      )}
      <div className="max-h-56 overflow-y-auto">
        {loading && <div className="px-3 py-2 text-sm text-gray-400">Загрузка...</div>}
        {!loading && filtered.length === 0 && (
          <div className="px-3 py-2 text-sm text-gray-400">Ничего не найдено</div>
        )}
        {filtered.map((o) => {
          const isSelected = selected.includes(o.value)
          return (
            <button
              key={o.value}
              onClick={() => toggle(o.value)}
              className="flex items-center gap-2 w-full px-3 py-1.5 text-sm text-left hover:bg-gray-50 transition-colors"
            >
              <span
                className={`flex items-center justify-center w-4 h-4 rounded border shrink-0 ${
                  isSelected ? "bg-[#111827] border-[#111827]" : "border-gray-300"
                }`}
              >
                {isSelected && <Check className="w-3 h-3 text-white" />}
              </span>
              <span className="text-[#111827] truncate">{o.label}</span>
            </button>
          )
        })}
      </div>
      {selected.length > 0 && (
        <div className="border-t border-gray-100 px-3 py-1.5">
          <button
            onClick={() => onChange([])}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            Сбросить
          </button>
        </div>
      )}
    </div>
  )
}
