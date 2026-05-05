"use client"

import { useCallback, useEffect, useRef } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { pipelineApi, profileApi, type PipelineStatus } from "@/lib/api"
import { Eye, FileEdit, Send, Trophy, XCircle } from "lucide-react"
import { useState } from "react"

const STATUSES: { value: PipelineStatus; label: string; icon: typeof Eye }[] = [
  { value: "studying", label: "Изучаю", icon: Eye },
  { value: "preparing", label: "Готовлю", icon: FileEdit },
  { value: "submitted", label: "Подал", icon: Send },
  { value: "won", label: "Выиграл", icon: Trophy },
  { value: "lost", label: "Проиграл", icon: XCircle },
]

export function PipelineStatusButtons({ tenderId, profileId: profileIdProp }: { tenderId: number; profileId?: number | null }) {
  const qc = useQueryClient()
  const [notes, setNotes] = useState("")
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  const { data: companies = [], isPending: companiesLoading } = useQuery({
    queryKey: ["companies"],
    queryFn: () => profileApi.listCompanies(),
    staleTime: 5 * 60 * 1000,
    enabled: profileIdProp == null,
  })
  // Use URL param if provided, otherwise fall back to first company
  const resolvedProfileId = profileIdProp ?? companies[0]?.id ?? null

  const { data: entry, isLoading } = useQuery({
    queryKey: ["pipeline", tenderId],
    queryFn: () => pipelineApi.byTender(tenderId),
  })

  useEffect(() => {
    if (entry?.notes !== undefined) setNotes(entry.notes)
  }, [entry?.notes])

  const invalidate = useCallback(() => {
    qc.invalidateQueries({ queryKey: ["pipeline", tenderId] })
    qc.invalidateQueries({ queryKey: ["pipeline-list"] })
    qc.invalidateQueries({ queryKey: ["pipeline-summary"] })
  }, [qc, tenderId])

  const createMut = useMutation({
    mutationFn: (status: PipelineStatus) =>
      pipelineApi.create(tenderId, status, resolvedProfileId),
    onSuccess: invalidate,
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { status?: PipelineStatus; notes?: string } }) =>
      pipelineApi.update(id, data),
    onSuccess: invalidate,
  })

  const removeMut = useMutation({
    mutationFn: (id: number) => pipelineApi.remove(id),
    onSuccess: () => {
      setNotes("")
      invalidate()
    },
  })

  const handleClick = (status: PipelineStatus) => {
    if (!entry) {
      createMut.mutate(status)
    } else if (entry.status === status) {
      removeMut.mutate(entry.id)
    } else {
      updateMut.mutate({ id: entry.id, data: { status } })
    }
  }

  const handleNotesChange = (value: string) => {
    setNotes(value)
    if (!entry) return
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      updateMut.mutate({ id: entry.id, data: { notes: value } })
    }, 1000)
  }

  if (isLoading || (profileIdProp == null && companiesLoading)) return null

  const busy = createMut.isPending || updateMut.isPending || removeMut.isPending

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium text-gray-500 uppercase tracking-wide">
          Участие в тендере
        </p>
        {resolvedProfileId != null && (
          <span className="text-xs text-gray-400">
            {companies.find((c) => c.id === resolvedProfileId)?.name || activeProfile?.name || "Компания"}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {STATUSES.map(({ value, label, icon: Icon }) => {
          const active = entry?.status === value
          return (
            <button
              key={value}
              onClick={() => handleClick(value)}
              disabled={busy}
              className={`
                inline-flex items-center gap-2 px-4 py-2 text-sm font-medium border transition-colors
                ${active
                  ? "bg-violet-100 border-violet-300 text-violet-800"
                  : "bg-white border-gray-200 text-gray-600 hover:border-gray-300 hover:text-gray-900"
                }
                disabled:opacity-50
              `}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          )
        })}
      </div>

      {entry && (
        <textarea
          value={notes}
          onChange={(e) => handleNotesChange(e.target.value)}
          placeholder="Заметки по этому тендеру..."
          rows={2}
          className="w-full px-3 py-2 text-sm border border-gray-200 bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-400 resize-y"
        />
      )}
    </div>
  )
}
