"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAuthenticated } from "@/lib/auth"
import { pipelineApi, type PipelineStatus, type TenderPipelineEntry } from "@/lib/api"
import Link from "next/link"
import { Briefcase, Trophy, XCircle } from "lucide-react"
import { DragDropContext, Droppable, Draggable, type DropResult } from "@hello-pangea/dnd"

const COLUMNS: { status: PipelineStatus; label: string; color: string }[] = [
  { status: "studying", label: "Изучаю", color: "border-t-blue-400" },
  { status: "preparing", label: "Готовлю", color: "border-t-amber-400" },
  { status: "submitted", label: "Подал", color: "border-t-violet-400" },
  { status: "won", label: "Выиграл", color: "border-t-emerald-400" },
  { status: "lost", label: "Проиграно", color: "border-t-gray-400" },
]

function fmt(n: number | null | undefined) {
  if (n == null) return "—"
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 0,
  }).format(n)
}

function fmtDate(s: string | null) {
  if (!s) return null
  return new Date(s).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  })
}

function SummaryCards() {
  const { data } = useQuery({
    queryKey: ["pipeline-summary"],
    queryFn: pipelineApi.summary,
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

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ["pipeline-list"],
    queryFn: pipelineApi.list,
  })

  const updateMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: PipelineStatus }) =>
      pipelineApi.update(id, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipeline-list"] })
      qc.invalidateQueries({ queryKey: ["pipeline-summary"] })
    },
  })

  const handleDragEnd = (result: DropResult) => {
    const { draggableId, destination } = result
    if (!destination) return

    const newStatus = destination.droppableId as PipelineStatus
    const entry = entries.find((e) => String(e.id) === draggableId)
    if (!entry || entry.status === newStatus) return

    qc.setQueryData<TenderPipelineEntry[]>(["pipeline-list"], (old) =>
      old?.map((e) => (e.id === entry.id ? { ...e, status: newStatus } : e))
    )

    updateMut.mutate({ id: entry.id, status: newStatus })
  }

  const grouped = COLUMNS.map((col) => ({
    ...col,
    entries: entries.filter((e) => e.status === col.status),
  }))

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-bold text-[#111827] mb-6">Мои тендеры</h1>

      <SummaryCards />

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
