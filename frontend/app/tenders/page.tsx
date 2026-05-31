"use client"

import { Suspense, useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useMutation, useQuery, useInfiniteQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { tendersApi, searchApi, directionsApi, pipelineApi, profileApi, type Tender, type PipelineStatus, type CompanyProfile } from "@/lib/api"
import { TenderCard } from "@/components/tender-card"
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import { getDirectionColor } from "@/lib/direction-colors"
import { Search, X, Sparkles, Building2, ChevronDown, ArrowUpDown } from "lucide-react"
import Link from "next/link"
import { useTenderFilters, filtersToApiParams, filtersToSearchBody, type TenderFilters } from "@/hooks/use-tender-filters"
import { FilterBar } from "@/components/filters/filter-bar"


type Tab = "all" | "match"

function usePipelineActions(profileId: number | null = null) {
  const qc = useQueryClient()
  const authed = isAuthenticated()

  const { data: entries = [] } = useQuery({
    queryKey: ["pipeline-list"],
    queryFn: () => pipelineApi.list(),
    enabled: authed,
  })

  const pipelineMap = new Map<number, { status: PipelineStatus; entryId: number }>()
  for (const e of entries) pipelineMap.set(e.tender, { status: e.status, entryId: e.id })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["pipeline-list"] })
    qc.invalidateQueries({ queryKey: ["pipeline-summary"] })
  }

  const createMut = useMutation({
    mutationFn: ({ tenderId, status }: { tenderId: number; status: PipelineStatus }) =>
      pipelineApi.create(tenderId, status, profileId),
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
  const [query, setQuery] = useState("")
  const [input, setInput] = useState("")
  const [page, setPage] = useState(1)
  const [allTenders, setAllTenders] = useState<Tender[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null)
  const authed = isAuthenticated()
  const { pipelineMap, setStatus, removeEntry } = usePipelineActions(selectedProfileId)

  const { data: companies = [] } = useQuery<CompanyProfile[]>({
    queryKey: ["companies"],
    queryFn: () => profileApi.listCompanies(),
    staleTime: 5 * 60 * 1000,
    enabled: authed,
  })

  // Default to first (most recently created) profile
  useEffect(() => {
    if (companies.length > 0 && !selectedProfileId) {
      setSelectedProfileId(companies[0].id)
    }
  }, [companies, selectedProfileId])

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
    enabled: !!query && authed,
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
      {/* Profile selector + Search bar */}
      <div className="flex items-center gap-3 px-6 py-3.5 border-b border-gray-200 shrink-0">
        {companies.length > 1 && (
          <ProfileSelector
            companies={companies}
            selectedId={selectedProfileId}
            onSelect={(id) => setSelectedProfileId(id)}
          />
        )}
        <form onSubmit={handleSearch} className="flex items-center gap-3 flex-1">
          <div className="relative flex-1 max-w-full sm:max-w-lg">
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
                return <TenderCard key={t.id} tender={t} pipelineStatus={p?.status} pipelineEntryId={p?.entryId} onSetPipelineStatus={authed ? setStatus : undefined} onRemoveFromPipeline={authed ? removeEntry : undefined} profileId={selectedProfileId} />
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

// ─── Profile selector dropdown ────────────────────────────────────────────────

function ProfileSelector({
  companies,
  selectedId,
  onSelect,
}: {
  companies: CompanyProfile[]
  selectedId: number | null
  onSelect: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  const selected = companies.find((c) => c.id === selectedId)

  if (companies.length <= 1) return null

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 h-8 px-3 text-sm border border-gray-200 text-gray-700 hover:border-gray-300 hover:text-[#111827] transition-colors"
      >
        <Building2 className="w-3.5 h-3.5 text-gray-400" />
        <span className="max-w-[160px] truncate">{selected?.name || "Выбрать компанию"}</span>
        <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 min-w-[200px] border border-gray-200 bg-white shadow-lg">
          {companies.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => { onSelect(c.id); setOpen(false) }}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
                c.id === selectedId ? "bg-gray-50 text-[#111827] font-medium" : "text-gray-700 hover:bg-gray-50"
              }`}
            >
              <span className="flex-1 truncate">{c.name || "Без названия"}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Match tab ────────────────────────────────────────────────────────────────

const SORT_OPTIONS = [
  { value: "score", label: "По релевантности" },
  { value: "deadline", label: "По дедлайну" },
  { value: "published", label: "По дате публикации" },
  { value: "nmck_asc", label: "По НМЦК ↑" },
  { value: "nmck_desc", label: "По НМЦК ↓" },
] as const

function MatchTab({ filters }: { filters: TenderFilters }) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [selectedDirId, setSelectedDirId] = useState<number | null>(null)
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null)
  const [sortBy, setSortBy] = useState(() => searchParams.get("sort") || "score")
  const { pipelineMap, setStatus, removeEntry } = usePipelineActions(selectedProfileId)

  function handleSortChange(value: string) {
    setSortBy(value)
    const params = new URLSearchParams(searchParams.toString())
    if (value === "score") {
      params.delete("sort")
    } else {
      params.set("sort", value)
    }
    router.replace(`/tenders?${params.toString()}`, { scroll: false })
  }

  const { data: companies = [] } = useQuery<CompanyProfile[]>({
    queryKey: ["companies"],
    queryFn: () => profileApi.listCompanies(),
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => {
    if (companies.length > 0 && !selectedProfileId) {
      setSelectedProfileId(companies[0].id)
    }
  }, [companies, selectedProfileId])

  const { data: directions = [] } = useQuery({
    queryKey: ["directions", selectedProfileId],
    queryFn: () => directionsApi.list(selectedProfileId ?? undefined),
    enabled: !!selectedProfileId,
  })

  useEffect(() => {
    if (directions.length > 0 && !selectedDirId) {
      setSelectedDirId(directions[0].id)
    }
  }, [directions, selectedDirId])

  const activeIds = selectedDirId ? [selectedDirId] : undefined

  const filterParams = filtersToApiParams(filters)
  const filterKey = JSON.stringify(filterParams)

  const {
    data,
    isFetching,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["match", activeIds, filterKey, selectedProfileId, sortBy],
    queryFn: ({ pageParam = 1 }) =>
      searchApi.match(20, activeIds, filterParams, selectedProfileId ?? undefined, pageParam, sortBy),
    getNextPageParam: (lastPage, allPages) =>
      lastPage.has_more ? allPages.length + 1 : undefined,
    initialPageParam: 1,
    retry: false,
    enabled: !!selectedDirId && !!selectedProfileId,
  })

  const tenders = data?.pages.flatMap((p) => p.data) ?? []
  const error = data?.pages[0]?.error

  const directionFilter = (
    <div className="flex items-center gap-2 px-6 py-3 border-b border-gray-200 shrink-0 flex-wrap">
      <ProfileSelector
        companies={companies}
        selectedId={selectedProfileId}
        onSelect={(id) => { setSelectedProfileId(id); setSelectedDirId(null) }}
      />
      {companies.length > 1 && directions.length > 0 && (
        <span className="w-px h-5 bg-gray-200 mx-0.5" />
      )}
      {directions.length > 0 && (
        <>
          <span className="text-xs text-gray-400 uppercase tracking-wide mr-1 select-none">Направление</span>
          {directions.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => setSelectedDirId(d.id)}
              className={`h-8 px-3.5 text-sm border transition-all duration-200 ${
                selectedDirId === d.id
                  ? "bg-violet-100 border-violet-300 text-violet-800 font-medium"
                  : "border-gray-300 text-gray-600 hover:bg-gray-100 hover:border-gray-400"
              }`}
            >
              {d.name || "Без названия"}
            </button>
          ))}
        </>
      )}
      <div className="ml-auto flex items-center gap-1.5">
        <ArrowUpDown className="w-3.5 h-3.5 text-gray-400" />
        <select
          value={sortBy}
          onChange={(e) => handleSortChange(e.target.value)}
          className="h-8 pl-1 pr-6 text-sm border border-gray-200 text-gray-600 bg-white hover:border-gray-300 transition-colors appearance-none cursor-pointer focus:outline-none"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
    </div>
  )

  if (directions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 h-48 gap-3">
        <Sparkles className="w-8 h-8 text-gray-300" />
        <p className="text-base text-gray-500">Заполните профиль компании, чтобы получать персональную подборку</p>
        <Link href="/profile" className="text-sm text-violet-600 hover:underline font-medium">
          Перейти в профиль
        </Link>
      </div>
    )
  }

  if (!selectedDirId) {
    return (
      <>
        {directionFilter}
        <div className="flex flex-col items-center justify-center flex-1 h-48 gap-3">
          <Sparkles className="w-8 h-8 text-gray-300" />
          <p className="text-sm text-gray-500">Выберите направление</p>
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
                return <TenderCard key={t.id} tender={t} pipelineStatus={p?.status} pipelineEntryId={p?.entryId} onSetPipelineStatus={setStatus} onRemoveFromPipeline={removeEntry} profileId={selectedProfileId} />
              })}
        {hasNextPage && (
          <div className="flex justify-center py-4">
            <button
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="text-xs text-muted-foreground hover:text-foreground transition-all duration-200 disabled:opacity-50"
            >
              {isFetchingNextPage ? "Загрузка..." : "Показать ещё"}
            </button>
          </div>
        )}
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

  const authed = isAuthenticated()

  const [showOnboarding, setShowOnboarding] = useState(false)
  const [regBannerDismissed, setRegBannerDismissed] = useState(() => typeof window !== "undefined" && localStorage.getItem("reg_banner_dismissed") === "1")
  useEffect(() => {
    if (!authed) return
    const dismissed = localStorage.getItem("onboarding_dismissed")
    if (dismissed) return
    profileApi.listCompanies().then((companies) => {
      if (companies.length === 0 || !companies[0].name) {
        setShowOnboarding(true)
      }
    }).catch(() => {})
  }, [authed])

  return (
    <div className="flex flex-col h-screen">
      {showOnboarding && (
        <div className="flex items-center justify-between px-6 h-16 bg-amber-50 border-b border-amber-200 text-base">
          <span className="text-amber-900">
            Заполните <Link href="/profile" className="underline font-medium">профиль компании</Link>, чтобы получать персональную подборку тендеров
          </span>
          <button
            onClick={() => { setShowOnboarding(false); localStorage.setItem("onboarding_dismissed", "1") }}
            className="text-amber-400 hover:text-amber-600 ml-4"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      )}
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
        {authed && (
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
        )}
      </div>

      <FilterBar
        filters={filters}
        setFilter={setFilter}
        setFilters={setFilters}
        clearAll={clearAll}
        activeCount={activeCount}
      />

      {!authed && !regBannerDismissed && (
        <div className="flex items-center justify-between px-6 h-16 bg-amber-50 border-b border-amber-200 text-base">
          <span className="text-amber-900">
            <Link href="/login" className="underline font-medium">Зарегистрируйтесь</Link>, чтобы получать персональную подборку тендеров, AI-анализ и многое другое
          </span>
          <button
            onClick={() => { setRegBannerDismissed(true); localStorage.setItem("reg_banner_dismissed", "1") }}
            className="text-amber-400 hover:text-amber-600 ml-4"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      )}

      <div key={tab} className="flex flex-col flex-1 min-h-0 animate-fade-in">
        {tab === "all" ? <AllTab filters={filters} /> : authed ? <MatchTab filters={filters} /> : <AllTab filters={filters} />}
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
