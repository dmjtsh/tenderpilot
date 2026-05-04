"use client"

interface Props {
  value: number | null
  onChange: (days: number | null) => void
}

const PRESETS = [
  { label: "3 дня", days: 3 },
  { label: "7 дней", days: 7 },
  { label: "14 дней", days: 14 },
  { label: "30 дней", days: 30 },
  { label: "60 дней", days: 60 },
]

export function DeadlineFilter({ value, onChange }: Props) {
  return (
    <div className="p-3 space-y-2">
      <p className="text-xs text-gray-500">Дедлайн подачи в течение:</p>
      <div className="flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.days}
            onClick={() => onChange(value === p.days ? null : p.days)}
            className={`h-7 px-2.5 text-xs border rounded-md transition-colors ${
              value === p.days
                ? "bg-[#111827] border-[#111827] text-white"
                : "border-gray-200 text-gray-600 hover:border-gray-300"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      {value !== null && (
        <button
          onClick={() => onChange(null)}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          Сбросить
        </button>
      )}
    </div>
  )
}
