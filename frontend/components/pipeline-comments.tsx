"use client"

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { pipelineApi } from "@/lib/api"
import { Send } from "lucide-react"

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "только что"
  if (mins < 60) return `${mins} мин. назад`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} ч. назад`
  const days = Math.floor(hours / 24)
  return `${days} дн. назад`
}

export function PipelineComments({ entryId }: { entryId: number }) {
  const qc = useQueryClient()
  const [text, setText] = useState("")

  const { data: comments = [], isLoading } = useQuery({
    queryKey: ["pipeline-comments", entryId],
    queryFn: () => pipelineApi.getComments(entryId),
  })

  const addMut = useMutation({
    mutationFn: (t: string) => pipelineApi.addComment(entryId, t),
    onSuccess: () => {
      setText("")
      qc.invalidateQueries({ queryKey: ["pipeline-comments", entryId] })
      qc.invalidateQueries({ queryKey: ["pipeline-activity", entryId] })
    },
  })

  const handleSubmit = () => {
    const trimmed = text.trim()
    if (!trimmed) return
    addMut.mutate(trimmed)
  }

  if (isLoading) return <div className="text-[15px] text-gray-400 py-6">Загрузка...</div>

  return (
    <div className="flex flex-col gap-4">
      {comments.length === 0 && (
        <p className="text-[15px] text-gray-400 py-6">Пока нет комментариев</p>
      )}
      {comments.map((c) => (
        <div key={c.id} className="flex gap-3">
          <div className="w-8 h-8 rounded-full bg-violet-100 text-violet-700 flex items-center justify-center text-sm font-semibold shrink-0">
            {c.user_name.charAt(0).toUpperCase()}
          </div>
          <div className="flex-1 bg-gray-50 rounded-lg px-4 py-2.5">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-gray-700">{c.user_name}</span>
              <span className="text-sm text-gray-400">{timeAgo(c.created_at)}</span>
            </div>
            <p className="text-[15px] text-gray-800 whitespace-pre-wrap">{c.text}</p>
          </div>
        </div>
      ))}
      <div className="flex gap-2.5 items-end mt-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Написать комментарий..."
          rows={2}
          className="flex-1 px-4 py-2.5 text-[15px] border border-gray-200 bg-white text-gray-900 placeholder:text-gray-400 focus:outline-none focus:border-gray-400 resize-none rounded"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit()
          }}
        />
        <button
          onClick={handleSubmit}
          disabled={addMut.isPending || !text.trim()}
          className="h-10 w-10 flex items-center justify-center bg-[#111827] text-white rounded hover:bg-gray-800 transition-colors disabled:opacity-40"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
