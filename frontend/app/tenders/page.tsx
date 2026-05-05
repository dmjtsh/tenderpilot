"use client"

import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { tendersApi, searchApi, directionsApi, pipelineApi, type Tender, type PipelineStatus } from "@/lib/api"
import { TenderCard } from "@/components/tender-card"
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { getDirectionColor } from "@/lib/direction-colors"
import { Search, X, Sparkles } from "lucide-react"
import Link from "next/link"
import { useTenderFilters, filtersToApiParams, filtersToSearchBody, type TenderFilters } from "@/hooks/use-tender-filters"
import { FilterBar } from "@/components/filters/filter-bar"


type Tab = "all" | "match"

function usePipelineActions() {
  const qc = useQueryClient()

  const { data: entries = [] } = useQuery({
    queryKey: ["pipeline-list"],
    queryFn: pipelineApi.list,
  })

  const pipelineMap = new Map<number, { status: PipelineStatus; entryId: number }>()
  for (const e of entries) pipelineMap.set(e.tender, { status: e.status, entryId: e.id })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["pipeline-list"] })
    qc.invalidateQueries({ queryKey: ["pipeline-summary"] })
  }

  const createMut = useMutation({
    mutationFn: ({ tenderId, status }: { tenderId: number; status: PipelineStatus }) =>
      pipelineApi.create(tenderId, status),
    onSuccess: invalidate,
  })

  const updateMut = useMutation({
    mutationFn: ({ entryId, status }: { entryId: number; status: PipelineStatus }) =>
      pipelineApi.update(entryId, { status }),
    onSuccess: invalidate,
  })

  const removeMut = useMutation({
    mutationFn: (entryId: number) => pipelineApi.remove(entryId),
    onSuccess: invalidate,
  })

  const setStatus = (tenderId: number, status: PipelineStatus, entryId?: number | null) => {
    if (entryId) {
      updateMut.mutate({ entryId, status })
    } else {
      createMut.mutate({ tenderId, status })
    }
  }

  const removeEntry = (entryId: number) => removeMut.mutate(entryId)

  return { pipelineMap, setStatus, removeEntry }
}

// ─── All tenders tab ─────────────────────────────────────────────────────────

function AllTab({ filters }: { filters: TenderFilters }) {
  const { pipelineMap, setStatus, removeEntry } = usePipelineActions()
  const [query, setQuery] = useState("")
  const [input, setInput] = useState("")
  const [page, setPage] = useState(1)
  const [allTenders, setAllTenders] = useState<Tender[]>([])

  const filterParams = filtersToApiParams(filters)
  const filterKey = JSON.stringify(filterParams)

  useEffect(() => {
    setPage(1)
    setAllTenders([])
  }, [filterKey])

  const { data: listData, isFetching: listFetching } = useQuery({
    queryKey: ["tenders", page, filterKey],
    queryFn: () => tendersApi.list(page, filterParams),
    enabled: !query,
  })

  const searchBody = filtersToSearchBody(filters)
  const { data: searchResults, isFetching: searchFetching } = useQuery({
    queryKey: ["search", query, filterKey],
    queryFn: () => searchApi.search(query, searchBody),
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
      <div className="flex items-center gap-3 px-6 py-3.5 border-b border-gray-200 shrink-0">
        <form onSubmit={handleSearch} className="flex items-center gap-3 flex-1">
          <div className="relative flex-1 max-w-lg">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400 pointer-events-none" />
            <input
              className="h-11 w-full pl-11 pr-4 text-base bg-gray-50 border border-gray-200 focus:border-gray-300 focus:outline-none text-gray-900 placeholder:text-gray-400 transition-all duration-200"
              placeholder="Семантический поиск..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
            />
          </div>
          {query && (
            <button type="button" onClick={handleClear} className="h-11 w-11 flex items-center justify-center text-gray-400 hover:text-gray-900 hover:bg-gray-100 transition-all duration-200">
              <X className="w-5 h-5" />
            </button>
          )}
          <button type="submit" className="h-11 px-6 text-base font-medium bg-[#111827] text-white hover:bg-[#1f2937] transition-all duration-200">
            Найти
          </button>
        </form>
        {query && (
          <span className="text-base text-gray-500">→ «{query}»</span>
        )}
      </div>

      {/* List */}
      <div className="flex-1 overflow-auto px-4 py-3 space-y-3">
        {isFetching && tenders.length === 0 && (
          <div className="flex items-center justify-center h-32">
            <span className="text-xs text-muted-foreground">Загрузка...</span>
          </div>
        )}
        {!isFetching && tenders.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 gap-1">
            <span className="text-sm text-muted-foreground">Ничего не найдено</span>
            {query && <button onClick={handleClear} className="text-xs text-violet-600 hover:underline">Сбросить поиск</button>}
          </div>
        )}
        {tenders.map((t) => {
                const p = pipelineMap.get(t.id)
                return <TenderCard key={t.id} tender={t} pipelineStatus={p?.status} pipelineEntryId={p?.entryId} onSetPipelineStatus={setStatus} onRemoveFromPipeline={removeEntry} />
              })}
        {hasMore && (
          <div className="flex justify-center py-4">
            <button onClick={() => setPage((p) => p + 1)} disabled={listFetching} className="text-xs text-muted-foreground hover:text-foreground transition-all duration-200 disabled:opacity-50">
              {listFetching ? "Загрузка..." : "Загрузить ещё"}
            </button>
          </div>
        )}
      </div>
    </>
  )
}

// ─── Match tab ────────────────────────────────────────────────────────────────

function MatchTab({ filters }: { filters: TenderFilters }) {
  const { pipelineMap, setStatus, removeEntry } = usePipelineActions()
  const [selectedIds, setSelectedIds] = useState<number[]>([])

  const { data: directions = [] } = useQuery({
    queryKey: ["directions"],
    queryFn: () => directionsApi.list(),
  })

  useEffect(() => {
    if (directions.length > 0 && selectedIds.length === 0) {
      setSelectedIds(directions.map((d) => d.id))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [directions])

  const noneSelected = selectedIds.length === 0
  const allSelected = directions.length > 0 && selectedIds.length === directions.length
  const activeIds = allSelected ? undefined : selectedIds

  const filterParams = filtersToApiParams(filters)
  const filterKey = JSON.stringify(filterParams)

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["match", activeIds, filterKey],
    queryFn: () => searchApi.match(20, activeIds, filterParams),
    retry: false,
    enabled: !noneSelected,
  })

  function toggleDirection(id: number) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  function toggleAll() {
    if (allSelected) {
      setSelectedIds([])
    } else {
      setSelectedIds(directions.map((d) => d.id))
    }
  }

  const tenders = data?.data ?? []
  const error = data?.error

  const directionFilter = directions.length > 1 ? (
    <div className="flex items-center gap-2 px-6 py-3 border-b border-gray-200 shrink-0 flex-wrap">
      <span className="text-xs text-gray-400 uppercase tracking-wide mr-1 select-none">Направления</span>
      <button
        type="button"
        onClick={toggleAll}
        className={`h-8 px-3.5 text-sm border transition-all duration-200 ${
          allSelected
            ? "bg-[#111827] border-[#111827] text-white font-medium"
            : "border-gray-300 text-gray-600 hover:bg-gray-100 hover:border-gray-400"
        }`}
      >
        Все
      </button>
      <span className="w-px h-5 bg-gray-200 mx-0.5" />
      {directions.map((d) => {
        const active = selectedIds.includes(d.id)
        return (
          <button
            key={d.id}
            type="button"
            onClick={() => toggleDirection(d.id)}
            className={`h-8 px-3.5 text-sm border transition-all duration-200 ${
              active
                ? "bg-violet-100 border-violet-300 text-violet-800 font-medium"
                : "border-gray-300 text-gray-600 hover:bg-gray-100 hover:border-gray-400"
            }`}
          >
            {d.name || "Без названия"}
          </button>
        )
      })}
    </div>
  ) : null

  if (noneSelected) {
    return (
      <>
        {directionFilter}
        <div className="flex flex-col items-center justify-center flex-1 h-48 gap-3">
          <Sparkles className="w-8 h-8 text-gray-300" />
          <p className="text-sm text-gray-500">Выберите хотя бы одно направление</p>
        </div>
      </>
    )
  }

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
          <Sparkles className="w-8 h-8 text-gray-300" />
          <p className="text-sm text-gray-500 text-center max-w-xs">{error}</p>
          <Link href="/profile" className="text-xs text-violet-600 hover:underline">
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
          <Sparkles className="w-8 h-8 text-gray-300" />
          <p className="text-sm text-gray-500">Подходящих тендеров не найдено</p>
          <button onClick={() => refetch()} className="text-xs text-violet-600 hover:underline">Обновить</button>
        </div>
      </>
    )
  }

  return (
    <>
      {directionFilter}
      <div className="flex-1 overflow-auto px-4 py-3 space-y-3">
        {tenders.map((t) => {
                const p = pipelineMap.get(t.id)
                return <TenderCard key={t.id} tender={t} pipelineStatus={p?.status} pipelineEntryId={p?.entryId} onSetPipelineStatus={setStatus} onRemoveFromPipeline={removeEntry} />
              })}
      </div>
    </>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

function TendersPageInner() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [tab, setTab] = useState<Tab>(() =>
    searchParams.get("tab") === "match" ? "match" : "all"
  )
  const { filters, setFilter, setFilters, clearAll, activeCount } = useTenderFilters()

  function handleTabChange(t: Tab) {
    setTab(t)
    const params = new URLSearchParams(searchParams.toString())
    if (t === "match") {
      params.set("tab", "match")
    } else {
      params.delete("tab")
    }
    router.replace(`/tenders?${params.toString()}`, { scroll: false })
  }

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  return (
    <div className="flex flex-col h-screen">
      {/* Top bar with tabs */}
      <div className="h-16 flex items-center gap-2 px-6 border-b border-gray-200 shrink-0">
        <button
          onClick={() => handleTabChange("all")}
          className={`h-10 px-5 text-base font-medium transition-all duration-200 ${
            tab === "all"
              ? "bg-gray-100 text-[#111827]"
              : "text-gray-500 hover:text-[#111827] hover:bg-gray-50"
          }`}
        >
          Все тендеры
        </button>
        <button
          onClick={() => handleTabChange("match")}
          className={`h-10 px-5 text-base font-medium transition-all duration-200 border border-transparent ${
            tab === "match"
              ? "bg-violet-50 text-violet-700"
              : "text-violet-600 hover:bg-violet-50 hover:border-violet-200"
          }`}
        >
          <Sparkles className="w-4 h-4 inline mr-2 mb-px text-violet-500" />
          Для вас
        </button>
      </div>

      <FilterBar
        filters={filters}
        setFilter={setFilter}
        setFilters={setFilters}
        clearAll={clearAll}
        activeCount={activeCount}
      />

      <div key={tab} className="flex flex-col flex-1 min-h-0 animate-fade-in">
        {tab === "all" ? <AllTab filters={filters} /> : <MatchTab filters={filters} />}
      </div>
    </div>
  )
}

export default function TendersPage() {
  return (
    <Suspense>
      <TendersPageInner />
    </Suspense>
  )
}
