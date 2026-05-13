"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { pipelineApi, profileApi, type PipelineStatus, type TenderPipelineEntry } from "@/lib/api"
import Link from "next/link"
import { Briefcase, Trophy, XCircle, Building2, ChevronDown } from "lucide-react"
import { DragDropContext, Droppable, Draggable, type DropResult } from "@hello-pangea/dnd"

const COLUMNS: { status: PipelineStatus; label: string; color: string }[] = [
  { status: "studying", label: "Изучаю", color: "border-t-blue-400" },
  { status: "preparing", label: "Готовлю", color: "border-t-amber-400" },
  { status: "submitted", label: "Подал", color: "border-t-violet-400" },
  { status: "won", label: "Выиграл", color: "border-t-emerald-400" },
  { status: "lost", label: "Проиграно", color: "border-t-gray-400" },
]

function fmt(n: number | string | null | undefined) {
  if (n == null) return "—"
  const num = typeof n === "string" ? parseFloat(n) : n
  if (isNaN(num)) return "—"
  return num.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + "\u00A0₽"
}

function fmtDate(s: string | null) {
  if (!s) return null
  return new Date(s).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  })
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

function PipelineCard({ entry, index }: { entry: TenderPipelineEntry; index: number }) {
  return (
    <Draggable draggableId={String(entry.id)} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          {...provided.dragHandleProps}
          className={`${snapshot.isDragging ? "shadow-lg ring-1 ring-violet-200" : ""}`}
        >
          <Link
            href={`/tenders/${entry.tender}`}
            className="block bg-white border border-gray-200 p-4 hover:border-gray-300 transition-colors"
          >
            <p className="text-xs font-mono text-gray-400 mb-1">{entry.tender_number}</p>
            <p className="text-sm font-medium text-[#111827] line-clamp-2 mb-2">
              {entry.tender_title}
            </p>
            <div className="flex items-center justify-between text-xs text-gray-500">
              <span>{fmt(entry.tender_nmck)}</span>
              {entry.tender_deadline_at && (
                <span>{fmtDate(entry.tender_deadline_at)}</span>
              )}
            </div>
            {entry.tender_region && (
              <p className="text-xs text-gray-400 mt-1 truncate">{entry.tender_region}</p>
            )}
          </Link>
        </div>
      )}
    </Draggable>
  )
}

export default function PipelinePage() {
  const router = useRouter()
  const qc = useQueryClient()
  // null = все компании (default — показываем все записи без фильтра)
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null)
  const [profileSelectorOpen, setProfileSelectorOpen] = useState(false)

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

  const grouped = COLUMNS.map((col) => ({
    ...col,
    entries: entries.filter((e) => e.status === col.status),
  }))

  const selectedCompany = companies.find((c) => c.id === selectedProfileId)

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-[#111827]">Мои тендеры</h1>

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
      ) : (
        <DragDropContext onDragEnd={handleDragEnd}>
          <div className="grid grid-cols-5 gap-4">
            {grouped.map((col) => (
              <div key={col.status}>
                <div
                  className={`border-t-2 ${col.color} bg-gray-50 px-3 py-2 mb-3`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-[#111827]">
                      {col.label}
                    </span>
                    <span className="text-xs text-gray-400">
                      {col.entries.length}
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
                        <PipelineCard key={entry.id} entry={entry} index={i} />
                      ))}
                      {provided.placeholder}
                    </div>
                  )}
                </Droppable>
              </div>
            ))}
          </div>
        </DragDropContext>
      )}
    </div>
  )
}
