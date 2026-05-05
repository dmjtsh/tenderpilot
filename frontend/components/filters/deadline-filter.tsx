"use client"

import { useState, useEffect } from "react"

interface Preset {
  label: string
  min: number | null
  max: number | null
}

const DEADLINE_PRESETS: Preset[] = [
  { label: "до 3 дн.", min: null, max: 3 },
  { label: "3–7 дн.", min: 3, max: 7 },
  { label: "7–14 дн.", min: 7, max: 14 },
  { label: "14–30 дн.", min: 14, max: 30 },
  { label: "30+ дн.", min: 30, max: null },
]

interface Props {
  min: number | null
  max: number | null
  onChangeMin: (days: number | null) => void
  onChangeMax: (days: number | null) => void
}

export function DeadlineFilter({ min, max, onChangeMin, onChangeMax }: Props) {
  const [customMin, setCustomMin] = useState("")
  const [customMax, setCustomMax] = useState("")
  const [showCustom, setShowCustom] = useState(false)

  useEffect(() => {
    const isPreset = DEADLINE_PRESETS.some((p) => p.min === min && p.max === max)
    if (!isPreset && (min !== null || max !== null)) {
      setShowCustom(true)
      setCustomMin(min !== null ? String(min) : "")
      setCustomMax(max !== null ? String(max) : "")
    }
  }, [min, max])

  const activePreset = DEADLINE_PRESETS.findIndex((p) => p.min === min && p.max === max)

  const selectPreset = (p: Preset, idx: number) => {
    if (activePreset === idx) {
      onChangeMin(null)
      onChangeMax(null)
      setShowCustom(false)
    } else {
      onChangeMin(p.min)
      onChangeMax(p.max)
      setShowCustom(false)
    }
  }

  const applyCustom = () => {
    onChangeMin(customMin ? Number(customMin) : null)
    onChangeMax(customMax ? Number(customMax) : null)
  }

  return (
    <div className="p-3 space-y-2.5">
      <p className="text-xs text-gray-500">Дней до дедлайна:</p>
      <div className="flex flex-wrap gap-1.5">
        {DEADLINE_PRESETS.map((p, i) => (
          <button
            key={i}
            onClick={() => selectPreset(p, i)}
            className={`h-7 px-2.5 text-xs border rounded-md transition-colors ${
              activePreset === i
                ? "bg-[#111827] border-[#111827] text-white"
                : "border-gray-200 text-gray-600 hover:border-gray-300"
            }`}
          >
            {p.label}
          </button>
        ))}
        <button
          onClick={() => {
            setShowCustom(!showCustom)
            if (!showCustom) {
              onChangeMin(null)
              onChangeMax(null)
            }
          }}
          className={`h-7 px-2.5 text-xs border rounded-md transition-colors ${
            showCustom && activePreset === -1
              ? "bg-[#111827] border-[#111827] text-white"
              : "border-gray-200 text-gray-600 hover:border-gray-300"
          }`}
        >
          своё
        </button>
      </div>

      {showCustom && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            inputMode="numeric"
            value={customMin}
            onChange={(e) => setCustomMin(e.target.value)}
            onBlur={applyCustom}
            onKeyDown={(e) => { if (e.key === "Enter") applyCustom() }}
            placeholder="от"
            className="w-full h-8 px-2.5 text-sm border border-gray-200 rounded-md bg-gray-50 text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
          />
          <span className="text-gray-400 text-xs">—</span>
          <input
            type="text"
            inputMode="numeric"
            value={customMax}
            onChange={(e) => setCustomMax(e.target.value)}
            onBlur={applyCustom}
            onKeyDown={(e) => { if (e.key === "Enter") applyCustom() }}
            placeholder="до"
            className="w-full h-8 px-2.5 text-sm border border-gray-200 rounded-md bg-gray-50 text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
          />
        </div>
      )}

      {(min !== null || max !== null) && (
        <button
          onClick={() => {
            onChangeMin(null)
            onChangeMax(null)
            setShowCustom(false)
            setCustomMin("")
            setCustomMax("")
          }}
          className="text-xs text-gray-500 hover:text-gray-700"
        >
          Сбросить
        </button>
      )}
    </div>
  )
}
