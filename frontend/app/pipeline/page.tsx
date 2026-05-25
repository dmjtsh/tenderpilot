"use client"

import { useDeferredValue, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { pipelineApi, profileApi, type PipelineStatus, type TenderPipelineEntry } from "@/lib/api"
import Link from "next/link"
import {
  Briefcase, Trophy, XCircle, Building2, ChevronDown,
  Search, LayoutGrid, List, Plus, Clock,
} from "lucide-react"
import { deadlineInfo } from "@/lib/deadline"
import { DragDropContext, Droppable, Draggable, type DropResult } from "@hello-pangea/dnd"
import { PipelineSidePanel } from "@/components/pipeline-side-panel"
import { PipelineListView } from "@/components/pipeline-list-view"

const COLUMNS: { status: PipelineStatus; label: string; color: string }[] = [
  { status: "new", label: "Новые", color: "border-t-slate-400" },
  { status: "studying", label: "Изучаю", color: "border-t-blue-400" },
  { status: "preparing", label: "Готовлю", color: "border-t-amber-400" },
  { status: "submitted", label: "Подал", color: "border-t-violet-400" },
  { status: "won", label: "Выиграл", color: "border-t-emerald-400" },
  { status: "lost", label: "Проиграно", color: "border-t-gray-400" },
]

function fmt(n: number | string | null | undefined) {
  if (n == null) return "Не указано"
  const num = typeof n === "string" ? parseFloat(n) : n
  if (isNaN(num)) return "Не указано"
  return num.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + "\u00A0₽"
}


function fmtSum(entries: TenderPipelineEntry[]): string | null {
  const total = entries.reduce((s, e) => s + (Number(e.tender_nmck) || 0), 0)
  if (total === 0) return null
  if (total >= 1_000_000_000) return (total / 1_000_000_000).toFixed(1) + " млрд"
  if (total >= 1_000_000) return (total / 1_000_000).toFixed(1) + " млн"
  return (total / 1_000).toFixed(0) + " тыс"
}

const RISK_BADGE: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-green-50 text-green-700",
}

const RISK_LABEL: Record<string, string> = {
  high: "Высокий риск",
  medium: "Средний риск",
  low: "Низкий риск",
}

function SummaryCards({ profileId }: { profileId?: number | null }) {
  const { data } = useQuery({
    queryKey: ["pipeline-summary", profileId],
    queryFn: () => pipelineApi.summary(profileId),
  })

  if (!data) return null

  const cards = [
    {
      label: "В работе",
      count: data.in_work_count,
      sum: data.in_work_sum,
      icon: Briefcase,
      color: "text-violet-600",
    },
    {
      label: "Выиграно",
      count: data.won_count,
      sum: data.won_sum,
      icon: Trophy,
      color: "text-emerald-600",
    },
    {
      label: "Проиграно",
      count: data.lost_count,
      sum: data.lost_sum,
      icon: XCircle,
      color: "text-gray-500",
    },
  ]

  return (
    <div className="grid grid-cols-3 gap-4 mb-8">
      {cards.map((c) => (
        <div key={c.label} className="bg-white border border-gray-200 p-5">
          <div className="flex items-center gap-2 mb-2">
            <c.icon className={`w-5 h-5 ${c.color}`} />
            <span className="text-sm font-medium text-gray-500">{c.label}</span>
          </div>
          <p className="text-2xl font-bold text-[#111827]">{c.count}</p>
          <p className="text-sm text-gray-500 mt-1">{fmt(c.sum)}</p>
        </div>
      ))}
    </div>
  )
}

function PipelineCard({
  entry, index, onOpen,
}: {
  entry: TenderPipelineEntry
  index: number
  onOpen: (entry: TenderPipelineEntry) => void
}) {
  return (
    <Draggable draggableId={String(entry.id)} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          className={`${snapshot.isDragging ? "shadow-lg ring-1 ring-violet-200" : ""}`}
          onClick={() => onOpen(entry)}
        >
          <div className="bg-white border border-gray-200 p-4 hover:border-gray-300 transition-colors cursor-pointer">
            <p className="text-sm font-medium text-[#111827] line-clamp-2 mb-2">
              {entry.tender_title}
            </p>
            {entry.tender_customer_name && (
              <p className="text-xs text-gray-500 mb-2 truncate">{entry.tender_customer_name}</p>
            )}
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>{fmt(entry.tender_nmck)}</span>
              {(() => {
                const dl = deadlineInfo(entry.tender_deadline_at)
                if (!dl) return null
                return (
                  <span className={`flex items-center gap-1 ${dl.className}`}>
                    {dl.days <= 3 && dl.days >= 0 && <Clock className="w-3 h-3" />}
                    {dl.text}
                  </span>
                )
              })()}
            </div>
            {entry.tender_overall_risk && (
              <span className={`inline-block mt-2 px-2 py-0.5 text-xs font-medium rounded ${RISK_BADGE[entry.tender_overall_risk]}`}>
                {RISK_LABEL[entry.tender_overall_risk]}
              </span>
            )}
            {entry.tender_docs_total > 0 && (
              <div className="mt-2 pt-2 border-t border-gray-100">
                <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                  <span>{entry.tender_docs_done}/{entry.tender_docs_total} документов</span>
                </div>
                <div className="h-1 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-violet-400 rounded-full transition-all"
                    style={{ width: `${(entry.tender_docs_done / entry.tender_docs_total) * 100}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Draggable>
  )
}

export default function PipelinePage() {
  const router = useRouter()
  const qc = useQueryClient()
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null)
  const [profileSelectorOpen, setProfileSelectorOpen] = useState(false)
  const [view, setView] = useState<"board" | "list">("board")
  const [search, setSearch] = useState("")
  const deferredSearch = useDeferredValue(search)
  const [selectedEntry, setSelectedEntry] = useState<{ entryId: number; tenderId: number } | null>(null)

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  const { data: companies = [] } = useQuery({
    queryKey: ["companies"],
    queryFn: () => profileApi.listCompanies(),
  })

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["pipeline-list", selectedProfileId],
    queryFn: () => pipelineApi.list(selectedProfileId),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: PipelineStatus }) =>
      pipelineApi.update(id, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipeline-list", selectedProfileId] })
      qc.invalidateQueries({ queryKey: ["pipeline-summary", selectedProfileId] })
    },
  })

  const handleDragEnd = (result: DropResult) => {
    const { draggableId, destination } = result
    if (!destination) return

    const newStatus = destination.droppableId as PipelineStatus
    const entry = entries.find((e) => String(e.id) === draggableId)
    if (!entry || entry.status === newStatus) return

    qc.setQueryData<TenderPipelineEntry[]>(["pipeline-list", selectedProfileId], (old) =>
      old?.map((e) => (e.id === entry.id ? { ...e, status: newStatus } : e))
    )

    updateMut.mutate({ id: entry.id, status: newStatus })
  }

  const filtered = entries.filter((e) => {
    if (!deferredSearch) return true
    const q = deferredSearch.toLowerCase()
    return (
      e.tender_title.toLowerCase().includes(q) ||
      e.tender_number.toLowerCase().includes(q) ||
      e.tender_customer_name.toLowerCase().includes(q)
    )
  })

  const grouped = COLUMNS.map((col) => ({
    ...col,
    entries: filtered.filter((e) => e.status === col.status),
  }))

  const selectedCompany = companies.find((c) => c.id === selectedProfileId)

  const handleCardOpen = (entry: TenderPipelineEntry) => {
    setSelectedEntry({ entryId: entry.id, tenderId: entry.tender })
  }

  return (
    <div className="p-8 max-w-[1600px] mx-auto">
      {/* Topbar */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <h1 className="text-2xl font-bold text-[#111827] mr-auto">Мои тендеры</h1>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Поиск..."
            className="pl-9 pr-4 h-9 w-56 text-sm border border-gray-200 bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-400"
          />
        </div>

        {/* View toggle */}
        <div className="flex border border-gray-200 overflow-hidden">
          <button
            onClick={() => setView("board")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${
              view === "board" ? "bg-gray-100 text-gray-900" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <LayoutGrid className="w-4 h-4" />
            Доска
          </button>
          <button
            onClick={() => setView("list")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${
              view === "list" ? "bg-gray-100 text-gray-900" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <List className="w-4 h-4" />
            Список
          </button>
        </div>

        {/* Add tender */}
        <Link
          href="/tenders"
          className="inline-flex items-center gap-2 h-9 px-4 text-sm font-medium bg-[#111827] text-white hover:bg-gray-800 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Добавить тендер
        </Link>

        {/* Profile selector */}
        {companies.length > 1 && (
          <div className="relative">
            <button
              onClick={() => setProfileSelectorOpen((v) => !v)}
              className="flex items-center gap-2 h-9 px-4 text-sm font-medium border border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:text-[#111827] transition-colors"
            >
              <Building2 className="w-4 h-4 text-gray-400" />
              <span>{selectedCompany?.name || "Все компании"}</span>
              <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${profileSelectorOpen ? "rotate-180" : ""}`} />
            </button>
            {profileSelectorOpen && (
              <div className="absolute right-0 mt-1 w-56 bg-white border border-gray-200 shadow-lg z-10">
                <button
                  onClick={() => { setSelectedProfileId(null); setProfileSelectorOpen(false) }}
                  className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm text-left hover:bg-gray-50 transition-colors ${selectedProfileId === null ? "font-medium text-[#111827]" : "text-gray-600"}`}
                >
                  Все компании
                </button>
                {companies.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => { setSelectedProfileId(c.id); setProfileSelectorOpen(false) }}
                    className={`w-full flex items-center gap-2 px-4 py-2.5 text-sm text-left hover:bg-gray-50 transition-colors ${selectedProfileId === c.id ? "font-medium text-[#111827]" : "text-gray-600"}`}
                  >
                    <Building2 className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                    <span className="truncate">{c.name || "Без названия"}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <SummaryCards profileId={selectedProfileId} />

      {isLoading ? (
        <div className="text-gray-400 text-sm">Загрузка...</div>
      ) : entries.length === 0 ? (
        <div className="text-center py-16">
          <p className="text-gray-500 text-base mb-2">Пока пусто</p>
          <p className="text-gray-400 text-sm">
            Откройте тендер и выберите статус участия
          </p>
        </div>
      ) : view === "board" ? (
        <DragDropContext onDragEnd={handleDragEnd}>
          <div className="grid grid-cols-6 gap-4">
            {grouped.map((col) => (
              <div key={col.status}>
                <div className={`border-t-2 ${col.color} bg-gray-50 px-3 py-2 mb-3`}>
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-[#111827]">
                      {col.label}
                    </span>
                    <span className="text-xs text-gray-400">
                      {col.entries.length}
                      {fmtSum(col.entries) && (
                        <span className="ml-1 text-gray-300">{fmtSum(col.entries)}</span>
                      )}
                    </span>
                  </div>
                </div>
                <Droppable droppableId={col.status}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.droppableProps}
                      className={`space-y-3 min-h-[100px] rounded transition-colors ${
                        snapshot.isDraggingOver ? "bg-violet-50/50" : ""
                      }`}
                    >
                      {col.entries.map((entry, i) => (
                        <PipelineCard key={entry.id} entry={entry} index={i} onOpen={handleCardOpen} />
                      ))}
                      {provided.placeholder}
                    </div>
                  )}
                </Droppable>
              </div>
            ))}
          </div>
        </DragDropContext>
      ) : (
        <PipelineListView entries={filtered} onOpen={handleCardOpen} />
      )}

      {/* Side Panel */}
      {selectedEntry && (
        <PipelineSidePanel
          entryId={selectedEntry.entryId}
          tenderId={selectedEntry.tenderId}
          onClose={() => setSelectedEntry(null)}
          onStatusChange={() => {
            qc.invalidateQueries({ queryKey: ["pipeline-list", selectedProfileId] })
            qc.invalidateQueries({ queryKey: ["pipeline-summary", selectedProfileId] })
          }}
        />
      )}
    </div>
  )
}
