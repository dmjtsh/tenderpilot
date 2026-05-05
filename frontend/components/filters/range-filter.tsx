"use client"

import { useState, useEffect } from "react"

interface Preset {
  label: string
  min: number | null
  max: number | null
}

const NMCK_PRESETS: Preset[] = [
  { label: "до 1 млн", min: null, max: 1_000_000 },
  { label: "1–10 млн", min: 1_000_000, max: 10_000_000 },
  { label: "10–50 млн", min: 10_000_000, max: 50_000_000 },
  { label: "50–200 млн", min: 50_000_000, max: 200_000_000 },
  { label: "200+ млн", min: 200_000_000, max: null },
]

interface Props {
  min: number | null
  max: number | null
  onChange: (min: number | null, max: number | null) => void
}

export function RangeFilter({ min, max, onChange }: Props) {
  const [customMin, setCustomMin] = useState("")
  const [customMax, setCustomMax] = useState("")
  const [showCustom, setShowCustom] = useState(false)

  useEffect(() => {
    const isPreset = NMCK_PRESETS.some((p) => p.min === min && p.max === max)
    if (!isPreset && (min !== null || max !== null)) {
      setShowCustom(true)
      setCustomMin(min !== null ? String(min) : "")
      setCustomMax(max !== null ? String(max) : "")
    }
  }, [min, max])

  const activePreset = NMCK_PRESETS.findIndex((p) => p.min === min && p.max === max)

  const selectPreset = (p: Preset, idx: number) => {
    if (activePreset === idx) {
      onChange(null, null)
      setShowCustom(false)
    } else {
      onChange(p.min, p.max)
      setShowCustom(false)
    }
  }

  const applyCustom = () => {
    const mi = customMin ? Number(customMin) : null
    const ma = customMax ? Number(customMax) : null
    onChange(mi, ma)
  }

  return (
    <div className="p-3 space-y-2.5">
      <div className="flex flex-wrap gap-1.5">
        {NMCK_PRESETS.map((p, i) => (
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
            if (!showCustom) onChange(null, null)
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
            value={customMin}
            onChange={(e) => setCustomMin(e.target.value)}
            onBlur={applyCustom}
            placeholder="от"
            className="w-full h-8 px-2.5 text-sm border border-gray-200 rounded-md bg-gray-50 text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
          />
          <span className="text-gray-400 text-xs">—</span>
          <input
            value={customMax}
            onChange={(e) => setCustomMax(e.target.value)}
            onBlur={applyCustom}
            placeholder="до"
            className="w-full h-8 px-2.5 text-sm border border-gray-200 rounded-md bg-gray-50 text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300"
          />
        </div>
      )}

      {(min !== null || max !== null) && (
        <button
          onClick={() => {
            onChange(null, null)
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
