"use client"

import { useQuery } from "@tanstack/react-query"
import { pipelineApi } from "@/lib/api"

const STATUS_LABELS: Record<string, string> = {
  new: "Новый",
  studying: "Изучаю",
  preparing: "Готовлю",
  submitted: "Подал",
  won: "Выиграл",
  lost: "Проиграно",
}

const ACTION_DOT: Record<string, string> = {
  created: "bg-slate-400",
  status_changed: "bg-violet-400",
  comment_added: "bg-blue-400",
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return "только что"
  if (mins < 60) return `${mins} мин. назад`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours} ч. назад`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days} дн. назад`
  return new Date(dateStr).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })
}

function renderAction(a: { action_type: string; old_value: string; new_value: string; user_name: string }) {
  switch (a.action_type) {
    case "created":
      return (
        <>
          <span className="font-medium text-gray-700">{a.user_name}</span>
          {" "}добавил тендер в пайплайн
          {a.new_value && <> со статусом <span className="font-medium">{STATUS_LABELS[a.new_value] || a.new_value}</span></>}
        </>
      )
    case "status_changed":
      return (
        <>
          <span className="font-medium text-gray-700">{a.user_name}</span>
          {" "}сменил статус: {STATUS_LABELS[a.old_value] || a.old_value} → {STATUS_LABELS[a.new_value] || a.new_value}
        </>
      )
    case "comment_added":
      return (
        <>
          <span className="font-medium text-gray-700">{a.user_name}</span>
          {" "}добавил комментарий
        </>
      )
    default:
      return <span className="font-medium text-gray-700">{a.user_name}</span>
  }
}

export function PipelineActivity({ entryId }: { entryId: number }) {
  const { data: activities = [], isLoading } = useQuery({
    queryKey: ["pipeline-activity", entryId],
    queryFn: () => pipelineApi.getActivity(entryId),
  })

  if (isLoading) return <div className="text-[15px] text-gray-400 py-6">Загрузка...</div>

  if (activities.length === 0) {
    return <p className="text-[15px] text-gray-400 py-6">Пока нет событий</p>
  }

  return (
    <div className="flex flex-col gap-5">
      {activities.map((a) => (
        <div key={a.id} className="flex gap-3 items-start">
          <div className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 ${ACTION_DOT[a.action_type] || "bg-gray-300"}`} />
          <div>
            <p className="text-[15px] text-gray-600">{renderAction(a)}</p>
            <p className="text-sm text-gray-400 mt-0.5">{timeAgo(a.created_at)}</p>
          </div>
        </div>
      ))}
    </div>
  )
}
