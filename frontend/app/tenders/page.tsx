"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { tendersApi, searchApi, directionsApi, type Tender } from "@/lib/api"
import { TenderCard } from "@/components/tender-card"
import { Search, X, Sparkles } from "lucide-react"
import Link from "next/link"

type Tab = "all" | "match"

// ─── All tenders tab ─────────────────────────────────────────────────────────

function AllTab() {
  const [query, setQuery] = useState("")
  const [input, setInput] = useState("")
  const [page, setPage] = useState(1)
  const [allTenders, setAllTenders] = useState<Tender[]>([])

  const { data: listData, isFetching: listFetching } = useQuery({
    queryKey: ["tenders", page],
    queryFn: () => tendersApi.list(page),
    enabled: !query,
  })

  const { data: searchResults, isFetching: searchFetching } = useQuery({
    queryKey: ["search", query],
    queryFn: () => searchApi.search(query),
    enabled: !!query,
  })

  useEffect(() => {
    if (!query && listData?.results) {
      setAllTenders((prev) => page === 1 ? listData.results : [...prev, ...listData.results])
    }
  }, [listData, page, query])

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setQuery(input.trim())
    setPage(1)
  }

  function handleClear() {
    setInput("")
    setQuery("")
    setPage(1)
    setAllTenders([])
  }

  const tenders = query ? (searchResults ?? []) : allTenders
  const isFetching = query ? searchFetching : listFetching
  const hasMore = !query && listData?.next != null

  return (
    <>
      {/* Search bar */}
      <div className="flex items-center gap-1.5 px-6 py-2.5 border-b border-border/50 shrink-0">
        <form onSubmit={handleSearch} className="flex items-center gap-1.5 flex-1">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
            <input
              className="h-7 w-full pl-8 pr-3 text-xs rounded-md bg-secondary border border-transparent focus:border-border focus:outline-none text-foreground placeholder:text-muted-foreground/60 transition-colors"
              placeholder="Семантический поиск..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
          </div>
          {query && (
            <button type="button" onClick={handleClear} className="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors">
              <X className="w-3.5 h-3.5" />
            </button>
          )}
          <button type="submit" className="h-7 px-3 text-xs font-medium rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors border border-border">
            Найти
          </button>
        </form>
        {query && (
          <span className="text-xs text-muted-foreground">→ «{query}»</span>
        )}
      </div>

      {/* Column headers */}
      <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border/50 shrink-0">
        <span className="w-3.5" />
        <span className="text-[10px] text-muted-foreground/60 uppercase tracking-wide w-[4.5rem] shrink-0">Номер</span>
        <span className="text-[10px] text-muted-foreground/60 uppercase tracking-wide flex-1">Название</span>
        <div className="flex items-center gap-5 shrink-0 text-[10px] text-muted-foreground/60 uppercase tracking-wide">
          <span className="hidden lg:block w-[180px]">Заказчик</span>
          <span className="w-[4.5rem] text-right">Дедлайн</span>
          <span className="w-[4.5rem] text-right">НМЦК</span>
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-auto">
        {isFetching && tenders.length === 0 && (
          <div className="flex items-center justify-center h-32">
            <span className="text-xs text-muted-foreground">Загрузка...</span>
          </div>
        )}
        {!isFetching && tenders.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 gap-1">
            <span className="text-sm text-muted-foreground">Ничего не найдено</span>
            {query && <button onClick={handleClear} className="text-xs text-primary hover:underline">Сбросить поиск</button>}
          </div>
        )}
        {tenders.map((t) => <TenderCard key={t.id} tender={t} />)}
        {hasMore && (
          <div className="flex justify-center py-4">
            <button onClick={() => setPage((p) => p + 1)} disabled={listFetching} className="text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50">
              {listFetching ? "Загрузка..." : "Загрузить ещё"}
            </button>
          </div>
        )}
      </div>
    </>
  )
}

// ─── Match tab ────────────────────────────────────────────────────────────────

function MatchTab() {
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  const { data: directions = [] } = useQuery({
    queryKey: ["directions"],
    queryFn: () => directionsApi.list(),
  })

  const activeIds = selectedIds.length > 0 ? selectedIds : undefined

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["match", activeIds],
    queryFn: () => searchApi.match(20, activeIds),
    retry: false,
  })

  function toggleDirection(id: number) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const tenders = data?.data ?? []
  const error = data?.error

  const directionFilter = directions.length > 1 ? (
    <div className="flex items-center gap-1.5 px-6 py-2 border-b border-border/50 shrink-0 flex-wrap">
      {directions.map((d) => {
        const active = selectedIds.includes(d.id)
        return (
          <button
            key={d.id}
            type="button"
            onClick={() => toggleDirection(d.id)}
            className={`h-6 px-2.5 text-xs rounded-md border transition-colors ${
              active
                ? "bg-primary/15 border-primary/40 text-primary"
                : "border-border/60 text-muted-foreground hover:border-border hover:text-foreground"
            }`}
          >
            {d.name || "Без названия"}
          </button>
        )
      })}
      {selectedIds.length > 0 && (
        <button
          type="button"
          onClick={() => setSelectedIds([])}
          className="h-6 px-2 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  ) : null

  if (isFetching) {
    return (
      <>
        {directionFilter}
        <div className="flex items-center justify-center flex-1 h-32">
          <span className="text-xs text-muted-foreground">Подбираем тендеры...</span>
        </div>
      </>
    )
  }

  if (error) {
    return (
      <>
        {directionFilter}
        <div className="flex flex-col items-center justify-center flex-1 h-48 gap-3">
          <Sparkles className="w-8 h-8 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground text-center max-w-xs">{error}</p>
          <Link href="/profile" className="text-xs text-primary hover:underline">
            Заполнить профиль →
          </Link>
        </div>
      </>
    )
  }

  if (tenders.length === 0) {
    return (
      <>
        {directionFilter}
        <div className="flex flex-col items-center justify-center flex-1 h-48 gap-3">
          <Sparkles className="w-8 h-8 text-muted-foreground/30" />
          <p className="text-sm text-muted-foreground">Подходящих тендеров не найдено</p>
          <button onClick={() => refetch()} className="text-xs text-primary hover:underline">Обновить</button>
        </div>
      </>
    )
  }

  return (
    <>
      {directionFilter}
      {/* Column headers */}
      <div className="flex items-center gap-3 px-4 py-1.5 border-b border-border/50 shrink-0">
        <span className="w-3.5" />
        <span className="text-[10px] text-muted-foreground/60 uppercase tracking-wide w-[4.5rem] shrink-0">Номер</span>
        <span className="text-[10px] text-muted-foreground/60 uppercase tracking-wide flex-1">Название</span>
        <div className="flex items-center gap-5 shrink-0 text-[10px] text-muted-foreground/60 uppercase tracking-wide">
          <span className="hidden lg:block w-[180px]">Заказчик</span>
          <span className="w-[4.5rem] text-right">Дедлайн</span>
          <span className="w-[4.5rem] text-right">НМЦК</span>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        {tenders.map((t) => <TenderCard key={t.id} tender={t} />)}
      </div>
    </>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function TendersPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [tab, setTab] = useState<Tab>(() =>
    searchParams.get("tab") === "match" ? "match" : "all"
  )

  function handleTabChange(t: Tab) {
    setTab(t)
    const url = t === "match" ? "/tenders?tab=match" : "/tenders"
    router.replace(url, { scroll: false })
  }

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  return (
    <div className="flex flex-col h-screen">
      {/* Top bar with tabs */}
      <div className="h-[52px] flex items-center gap-1 px-6 border-b border-border shrink-0">
        {([["all", "Все тендеры"], ["match", "Для вас"]] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => handleTabChange(id)}
            className={`h-7 px-3 text-xs rounded-md font-medium transition-colors ${
              tab === id
                ? "bg-secondary text-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-secondary/50"
            }`}
          >
            {id === "match" && <Sparkles className="w-3 h-3 inline mr-1.5 mb-px" />}
            {label}
          </button>
        ))}
      </div>

      {tab === "all" ? <AllTab /> : <MatchTab />}
    </div>
  )
}
