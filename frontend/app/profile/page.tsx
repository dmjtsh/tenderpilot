"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { isAuthenticated } from "@/lib/auth"
import { profileApi, directionsApi, tendersApi, billingApi, type CompanyProfile, type CompanyDirection, type WonTenderRef, type InnLookupResult, type UserPlan } from "@/lib/api"
import { ChevronDown, Search, X, Plus, Trash2, Loader2, Sparkles, Building2 } from "lucide-react"
import { OkvedCombobox } from "@/components/okved-combobox"

type FormValues = {
  name: string
  inn: string
}

function toForm(p: CompanyProfile): FormValues {
  return {
    name: p.name ?? "",
    inn: p.inn ?? "",
  }
}

function fromForm(f: FormValues): Partial<CompanyProfile> {
  return {
    name: f.name,
    inn: f.inn,
  }
}

// ─── RegionSelect ────────────────────────────────────────────────────────────

function RegionSelect({
  value,
  onChange,
  options,
}: {
  value: string[]
  onChange: (v: string[]) => void
  options: string[]
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onClickOutside)
    return () => document.removeEventListener("mousedown", onClickOutside)
  }, [])

  const filtered = options.filter((r) =>
    r.toLowerCase().includes(search.toLowerCase())
  )

  function toggle(region: string) {
    onChange(
      value.includes(region) ? value.filter((r) => r !== region) : [...value, region]
    )
  }

  const label =
    value.length === 0
      ? "Все регионы"
      : value.length === 1
      ? value[0]
      : `${value[0]} +${value.length - 1}`

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full h-8 flex items-center justify-between gap-2 rounded-md bg-secondary border border-border px-3 text-sm text-foreground hover:border-border/80 transition-colors"
      >
        <span className={value.length === 0 ? "text-muted-foreground/60" : ""}>
          {label}
        </span>
        <div className="flex items-center gap-1.5 shrink-0">
          {value.length > 0 && (
            <span
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={(e) => { e.stopPropagation(); onChange([]) }}
            >
              <X className="w-3 h-3" />
            </span>
          )}
          <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      {open && (
        <div className="absolute z-50 top-full mt-1 w-full rounded-md border border-border bg-popover shadow-lg overflow-hidden">
          <div className="flex items-center gap-2 px-2 py-1.5 border-b border-border">
            <Search className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
            <input
              autoFocus
              className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none"
              placeholder="Поиск региона..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="max-h-56 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="px-3 py-2 text-xs text-muted-foreground">Не найдено</p>
            ) : (
              filtered.map((region) => (
                <label
                  key={region}
                  className="flex items-center gap-2.5 px-3 py-1.5 text-sm cursor-pointer hover:bg-secondary/60 transition-colors"
                >
                  <input
                    type="checkbox"
                    checked={value.includes(region)}
                    onChange={() => toggle(region)}
                    className="w-3.5 h-3.5 accent-primary"
                  />
                  <span>{region}</span>
                </label>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── NMC ranges ──────────────────────────────────────────────────────────────

const NMCK_PRESETS = [
  { label: "Любая сумма", min: null, max: null },
  { label: "до 1 млн", min: null, max: 1_000_000 },
  { label: "1–10 млн", min: 1_000_000, max: 10_000_000 },
  { label: "10–50 млн", min: 10_000_000, max: 50_000_000 },
  { label: "50–200 млн", min: 50_000_000, max: 200_000_000 },
  { label: "свыше 200 млн", min: 200_000_000, max: null },
  { label: "своё", min: -1, max: -1 },
] as const

const LAW_TYPES = ["44-ФЗ", "223-ФЗ", "615-ПП", "b2b"] as const

const PROCEDURE_TYPES = [
  { value: "auction", label: "Аукцион" },
  { value: "contest", label: "Конкурс" },
  { value: "request_quotations", label: "Запрос котировок" },
  { value: "request_proposals", label: "Запрос предложений" },
  { value: "single_source", label: "Ед. поставщик" },
  { value: "other", label: "Иной способ" },
] as const


// ─── WonTendersSection ────────────────────────────────────────────────────────

function WonTendersSection({
  profile,
  onSave,
}: {
  profile: CompanyProfile
  onSave: (ids: number[]) => Promise<void>
}) {
  const qc = useQueryClient()
  const [wonIds, setWonIds] = useState<number[]>(profile.won_tender_ids ?? [])
  const [wonTenders, setWonTenders] = useState<WonTenderRef[]>(profile.won_tenders ?? [])
  const [url, setUrl] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // sync when profile changes (e.g. company switch) or after refetch
  useEffect(() => {
    setWonIds(profile.won_tender_ids ?? [])
    setWonTenders((prev) => {
      const incoming = profile.won_tenders ?? []
      // merge: keep local state for any ID not yet returned by server
      const byServerId = Object.fromEntries(incoming.map((t) => [t.id, t]))
      return (profile.won_tender_ids ?? []).map(
        (id) => byServerId[id] ?? prev.find((t) => t.id === id) ?? { id, number: String(id), title: "—", is_indexed: false, status: "" }
      )
    })
    setUrl("")
    setError(null)
  }, [profile.id, profile.won_tenders])

  // poll every 5s while any won tender is still indexing
  const hasUnindexed = wonTenders.some((t) => !t.is_indexed)
  useEffect(() => {
    if (!hasUnindexed) return
    const timer = setInterval(() => {
      qc.invalidateQueries({ queryKey: ["companies"] })
    }, 5000)
    return () => clearInterval(timer)
  }, [hasUnindexed, qc])

  async function handleAdd() {
    const val = url.trim()
    if (!val) return
    setLoading(true)
    setError(null)
    try {
      const res = await tendersApi.searchWonCandidates(val)
      if (res.error) { setError(res.error); return }
      if (res.data.length === 0) {
        setError("Тендер не найден в базе. Убедитесь что ссылка с zakupki.gov.ru и тендер у нас проиндексирован.")
        return
      }
      const t = res.data[0]
      if (wonIds.includes(t.id)) {
        setError("Этот тендер уже добавлен")
        return
      }
      const newIds = [...wonIds, t.id]
      const newTenders = [...wonTenders, t]
      setWonIds(newIds)
      setWonTenders(newTenders)
      setUrl("")
      setSaving(true)
      await onSave(newIds)
    } catch {
      setError("Ошибка при добавлении")
    } finally {
      setLoading(false)
      setSaving(false)
    }
  }

  async function handleRemove(id: number) {
    const newIds = wonIds.filter((x) => x !== id)
    setWonIds(newIds)
    setWonTenders((prev) => prev.filter((t) => t.id !== id))
    setSaving(true)
    try { await onSave(newIds) } finally { setSaving(false) }
  }

  const byId = Object.fromEntries(wonTenders.map((t) => [t.id, t]))
  const canAdd = wonIds.length < 3

  return (
    <div className="border border-gray-200 bg-white">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div>
          <p className="text-base font-semibold text-[#111827]">Выигранные тендеры</p>
          <p className="text-xs text-gray-400 mt-0.5">До 3 тендеров — улучшают ранжирование в «Для вас»</p>
        </div>
        {saving && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
      </div>

      <div className="px-6 py-5 space-y-4">
        {/* Chips */}
        {wonIds.length > 0 && (
          <div className="space-y-2">
            {wonIds.map((id) => {
              const t = byId[id]
              const indexing = t ? !t.is_indexed : false
              return (
                <div key={id} className="flex items-start gap-3 px-4 py-3 bg-violet-50 border border-violet-200">
                  <div className="flex-1 min-w-0">
                    <p className="font-mono text-xs text-violet-500 mb-0.5">№{t?.number ?? id}</p>
                    <p className="text-sm text-[#111827] leading-snug">{t?.title ?? "—"}</p>
                  </div>
                  {indexing && (
                    <span className="flex items-center gap-1 text-[10px] text-amber-500 shrink-0 self-center">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      индексируется
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => handleRemove(id)}
                    className="shrink-0 p-1 text-violet-300 hover:text-violet-600 transition-colors self-center"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              )
            })}
          </div>
        )}

        {/* URL input */}
        {canAdd ? (
          <div>
            <p className="text-sm text-gray-500 mb-2">Вставьте ссылку на тендер с zakupki.gov.ru</p>
            <div className="flex gap-2">
              <input
                className="flex-1 h-10 bg-gray-50 border border-gray-200 px-3 text-sm text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300 transition-colors"
                placeholder="https://zakupki.gov.ru/...?regNumber=..."
                value={url}
                onChange={(e) => { setUrl(e.target.value); setError(null) }}
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              />
              <button
                type="button"
                onClick={handleAdd}
                disabled={loading || !url.trim()}
                className="h-10 px-4 text-sm font-medium bg-[#111827] text-white hover:bg-[#1f2937] transition-colors disabled:opacity-50 flex items-center gap-2 shrink-0"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                Добавить
              </button>
            </div>
            {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
          </div>
        ) : (
          <p className="text-xs text-gray-400">Максимум 3 тендера добавлено</p>
        )}
      </div>
    </div>
  )
}

// ─── DirectionCard ────────────────────────────────────────────────────────────

function DirectionCard({
  direction,
  regionOptions,
  profileId,
  onDelete,
}: {
  direction: CompanyDirection
  regionOptions: string[]
  profileId?: number
  onDelete: () => void
}) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(!direction.vector_updated_at)

  const [name, setName] = useState(direction.name)
  const [description, setDescription] = useState(direction.description ?? "")
  const [okvedCodes, setOkvedCodes] = useState<string[]>(direction.okved_codes ?? [])
  const [keywords, setKeywords] = useState((direction.keywords ?? []).join(", "))
  const [excludeKeywords, setExcludeKeywords] = useState((direction.exclude_keywords ?? []).join(", "))
  const [regions, setRegions] = useState<string[]>(direction.regions ?? [])
  const [lawTypes, setLawTypes] = useState<string[]>(direction.law_types ?? [])
  const [procedureTypes, setProcedureTypes] = useState<string[]>(direction.procedure_types ?? [])
  const [nmckPreset, setNmckPreset] = useState(() => {
    if (direction.nmck_min === null && direction.nmck_max === null) return 0
    const idx = NMCK_PRESETS.findIndex(
      (p) => p.min === direction.nmck_min && p.max === direction.nmck_max
    )
    return idx >= 0 ? idx : NMCK_PRESETS.length - 1
  })
  const [customMin, setCustomMin] = useState(direction.nmck_min?.toString() ?? "")
  const [customMax, setCustomMax] = useState(direction.nmck_max?.toString() ?? "")

  const isCustom = nmckPreset === NMCK_PRESETS.length - 1

  const saveMutation = useMutation({
    mutationFn: () => {
      const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean)
      const preset = NMCK_PRESETS[nmckPreset]
      const nmck_min = isCustom ? (customMin ? parseInt(customMin) : null) : preset.min as number | null
      const nmck_max = isCustom ? (customMax ? parseInt(customMax) : null) : preset.max as number | null
      return directionsApi.update(direction.id, {
        name,
        description,
        okved_codes: okvedCodes,
        keywords: split(keywords),
        exclude_keywords: split(excludeKeywords),
        regions,
        law_types: lawTypes,
        procedure_types: procedureTypes,
        nmck_min,
        nmck_max,
      }, profileId)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["directions", profileId] })
      setExpanded(false)
    },
  })

  const isIndexing = !direction.vector_updated_at

  return (
    <div className="border border-gray-200 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <ChevronDown className={`w-4 h-4 text-gray-400 shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} />
        <span className="flex-1 text-base font-medium text-[#111827]">{name || "Новое направление"}</span>
        {isIndexing ? (
          <span className="flex items-center gap-1.5 text-[10px] text-amber-600">
            <Loader2 className="w-3 h-3 animate-spin" />
            индексируется
          </span>
        ) : (
          <span className="text-[10px] text-emerald-500">● активно</span>
        )}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="p-1 rounded text-muted-foreground/50 hover:text-destructive hover:bg-destructive/10 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Body */}
      {expanded && (
        <div className="px-5 pb-5 pt-2 space-y-5 border-t border-gray-200">
          {/* Name */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Название направления</p>
            <input
              className={inputCls}
              placeholder="Кровельные работы"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* Description */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Описание направления <span className="text-muted-foreground/50">(специфика работ, типы объектов, материалы)</span></p>
            <textarea
              className="w-full bg-gray-50 border border-gray-200 px-4 py-3 text-base text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300 transition-colors resize-none"
              rows={3}
              maxLength={500}
              placeholder="Капитальный ремонт мягкой кровли. Рулонные материалы, металлочерепица. Объекты: школы, детсады, жилые дома до 5 этажей."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          {/* OKVED */}
          <div>
            <p className="text-sm text-gray-500 mb-2">ОКВЭД коды</p>
            <OkvedCombobox value={okvedCodes} onChange={setOkvedCodes} />
          </div>

          {/* Keywords */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Ключевые слова <span className="text-muted-foreground/50">(через запятую)</span></p>
            <input
              className={inputCls}
              placeholder="кровля, кровельные работы"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
            />
          </div>

          {/* Exclude Keywords */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Слова-исключения <span className="text-muted-foreground/50">(через запятую, тендеры с этими словами в названии будут скрыты)</span></p>
            <input
              className={inputCls}
              placeholder="уборка, клининг, озеленение"
              value={excludeKeywords}
              onChange={(e) => setExcludeKeywords(e.target.value)}
            />
          </div>

          {/* Regions */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Регионы <span className="text-gray-400 font-normal">(необязательно)</span></p>
            <RegionSelect value={regions} onChange={setRegions} options={regionOptions} />
          </div>

          {/* NMC */}
          <div>
            <p className="text-sm text-gray-500 mb-2">НМЦК <span className="text-gray-400 font-normal">(необязательно)</span></p>
            <div className="flex flex-wrap gap-1.5">
              {NMCK_PRESETS.map((preset, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setNmckPreset(idx)}
                  className={`h-9 px-3.5 text-sm border transition-colors ${
                    nmckPreset === idx
                      ? "bg-[#111827] border-[#111827] text-white"
                      : "border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-900"
                  }`}
                >
                  {preset.label}
                </button>
              ))}
            </div>
            {isCustom && (
              <div className="flex items-center gap-2 mt-2">
                <input
                  className={`${inputCls} w-36`}
                  placeholder="от ₽"
                  value={customMin}
                  onChange={(e) => setCustomMin(e.target.value)}
                />
                <span className="text-xs text-muted-foreground">—</span>
                <input
                  className={`${inputCls} w-36`}
                  placeholder="до ₽"
                  value={customMax}
                  onChange={(e) => setCustomMax(e.target.value)}
                />
              </div>
            )}
          </div>

          {/* Law types */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Типы закупок <span className="text-gray-400 font-normal">(необязательно)</span></p>
            <div className="flex gap-4">
              {LAW_TYPES.map((lt) => (
                <label key={lt} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={lawTypes.includes(lt)}
                    onChange={() =>
                      setLawTypes((prev) =>
                        prev.includes(lt) ? prev.filter((x) => x !== lt) : [...prev, lt]
                      )
                    }
                    className="w-4 h-4 accent-[#111827]"
                  />
                  <span className="text-sm text-[#111827] font-mono">{lt}</span>
                </label>
              ))}
            </div>
            {lawTypes.length === 0 && (
              <p className="text-xs text-gray-400 mt-1.5">Если не выбрано — ищем по всем типам</p>
            )}
          </div>

          {/* Procedure types */}
          <div>
            <p className="text-sm text-gray-500 mb-2">Типы процедур <span className="text-gray-400 font-normal">(необязательно)</span></p>
            <div className="flex flex-wrap gap-4">
              {PROCEDURE_TYPES.map((pt) => (
                <label key={pt.value} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={procedureTypes.includes(pt.value)}
                    onChange={() =>
                      setProcedureTypes((prev) =>
                        prev.includes(pt.value) ? prev.filter((x) => x !== pt.value) : [...prev, pt.value]
                      )
                    }
                    className="w-4 h-4 accent-[#111827]"
                  />
                  <span className="text-sm text-[#111827]">{pt.label}</span>
                </label>
              ))}
            </div>
            {procedureTypes.length === 0 && (
              <p className="text-xs text-gray-400 mt-1.5">Если не выбрано — ищем по всем типам</p>
            )}
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="h-10 px-5 text-sm font-medium bg-[#111827] text-white hover:bg-[#1f2937] transition-colors disabled:opacity-50"
            >
              {saveMutation.isPending ? "Сохранение..." : "Сохранить"}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── DirectionsSection ────────────────────────────────────────────────────────

function DirectionsSection({ regionOptions, profileId }: { regionOptions: string[], profileId?: number }) {
  const qc = useQueryClient()

  const { data: directions = [], isPending, isFetching } = useQuery<CompanyDirection[]>({
    queryKey: ["directions", profileId],
    queryFn: () => directionsApi.list(profileId),
    enabled: !!profileId,
  })

  const createMutation = useMutation({
    mutationFn: () =>
      directionsApi.create({
        name: "",
        description: "",
        okved_codes: [],
        keywords: [],
        exclude_keywords: [],
        regions: [],
        law_types: [],
        procedure_types: [],
        nmck_min: null,
        nmck_max: null,
      }, profileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["directions", profileId] }),
    onError: (e: unknown) => console.error("create direction failed:", e),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => directionsApi.remove(id, profileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["directions", profileId] }),
  })

  const isLoading = isPending && isFetching

  return (
    <div>
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
        <p className="text-base font-semibold text-[#111827]">Направления поиска</p>
        <button
          type="button"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="flex items-center gap-2 h-10 px-4 text-sm font-medium border border-gray-200 text-gray-700 hover:text-[#111827] hover:border-gray-300 transition-colors disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          Добавить
        </button>
      </div>

      <div className="px-6 py-5">
        {isLoading ? (
          <p className="text-[15px] text-gray-500">Загрузка...</p>
        ) : directions.length === 0 ? (
          <p className="text-[15px] text-gray-500">
            Добавьте направления, чтобы получать персональные рекомендации тендеров.
          </p>
        ) : (
          <div className="space-y-3">
            {directions.map((d) => (
          <DirectionCard
                key={d.id}
                direction={d}
                regionOptions={regionOptions}
                profileId={profileId}
                onDelete={() => deleteMutation.mutate(d.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── ProfileCompleteness ─────────────────────────────────────────────────────

function ProfileCompleteness({
  profile,
  directions,
}: {
  profile: CompanyProfile
  directions: CompanyDirection[]
}) {
  const hasOkvedOrKeywords = directions.some(
    (d) => (d.okved_codes?.length ?? 0) > 0 || (d.keywords?.length ?? 0) > 0
  )
  const items = [
    { label: "Компания создана", done: !!profile.name },
    { label: "Хотя бы 1 направление", done: directions.length > 0 },
    { label: "ОКВЭД или ключевые слова указаны", done: hasOkvedOrKeywords },
    { label: "Описание направления (улучшает точность)", done: directions.some((d) => (d.description?.length ?? 0) >= 30) },
  ]
  const doneCount = items.filter((i) => i.done).length
  const percent = Math.round((doneCount / items.length) * 100)
  const allDone = doneCount === items.length

  if (allDone) {
    return (
      <div className="border border-emerald-200 bg-emerald-50/50 px-6 py-4 flex items-center gap-3">
        <span className="text-emerald-600 text-sm font-medium">Профиль полностью заполнен</span>
      </div>
    )
  }

  return (
    <div className="border border-gray-200 bg-white">
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center justify-between mb-3">
          <p className="text-base font-semibold text-[#111827]">Качество рекомендаций</p>
          <span className="text-sm font-medium text-violet-600">{percent}%</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-violet-600 rounded-full transition-all duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>
      <div className="px-6 py-4 space-y-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-3 text-sm">
            {item.done ? (
              <span className="text-emerald-500 w-5 text-center font-medium">&#10003;</span>
            ) : (
              <span className="text-gray-300 w-5 text-center">&#9675;</span>
            )}
            <span className={item.done ? "text-gray-500" : "text-gray-700"}>{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

const inputCls = "w-full h-11 bg-gray-50 border border-gray-200 px-4 text-base text-[#111827] placeholder:text-gray-400 focus:outline-none focus:border-gray-300 transition-colors"

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[200px_1fr] gap-5 items-start mb-4 last:mb-0">
      <div className="pt-2.5">
        <p className="text-[15px] text-[#111827]">{label}</p>
        {hint && <p className="text-sm text-gray-500 mt-0.5">{hint}</p>}
      </div>
      <div>{children}</div>
    </div>
  )
}

// ─── InnSuggestPanel ──────────────────────────────────────────────────────────

function InnSuggestPanel({
  result,
  onApply,
  onDismiss,
}: {
  result: InnLookupResult
  onApply: (selected: { okved_code: string; name: string }[]) => void
  onDismiss: () => void
}) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(result.suggested_directions.map((d) => d.okved_code))
  )

  function toggle(code: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(code)) { next.delete(code) } else { next.add(code) }
      return next
    })
  }

  return (
    <div className="mt-4 rounded-lg border border-violet-200 bg-violet-50/50 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-3.5 h-3.5 text-violet-600 shrink-0" />
        <p className="text-xs font-medium text-gray-900">
          Найдено: <span className="text-violet-600">{result.name}</span>
        </p>
        <button
          type="button"
          onClick={onDismiss}
          className="ml-auto text-muted-foreground/50 hover:text-muted-foreground"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {result.region && (
        <p className="text-xs text-muted-foreground">Регион: {result.region}</p>
      )}

      {result.suggested_directions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">Добавить направления по ОКВЭД:</p>
          <div className="space-y-1.5">
            {result.suggested_directions.map((d) => (
              <label
                key={d.okved_code}
                className="flex items-center gap-2.5 cursor-pointer group"
              >
                <input
                  type="checkbox"
                  checked={selected.has(d.okved_code)}
                  onChange={() => toggle(d.okved_code)}
                  className="w-3.5 h-3.5 accent-primary shrink-0"
                />
                <span className="font-mono text-[11px] text-muted-foreground w-10 shrink-0">
                  {d.okved_code}
                </span>
                <span className="text-xs text-foreground/80 group-hover:text-foreground transition-colors truncate">
                  {d.name}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() =>
          onApply(result.suggested_directions.filter((d) => selected.has(d.okved_code)))
        }
        className="h-7 px-3 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Применить
      </button>
    </div>
  )
}

// ─── PlanBlock ────────────────────────────────────────────────────────────────

const PLAN_LABEL: Record<string, string> = { free: "Free", standard: "Standard", premium: "Premium" }
const PLAN_COLOR: Record<string, string> = {
  free: "bg-gray-100 text-gray-600",
  standard: "bg-violet-100 text-violet-700",
  premium: "bg-amber-100 text-amber-700",
}

function UsageBar({ used, limit, label }: { used: number; limit: number; label: string }) {
  const pct = Math.min(100, Math.round((used / limit) * 100))
  const nearLimit = pct >= 80
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600">{label}</span>
        <span className={`font-medium tabular-nums ${nearLimit ? "text-amber-600" : "text-gray-700"}`}>
          {used} / {limit}
        </span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${nearLimit ? "bg-amber-500" : "bg-violet-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function PlanBlock({ plan }: { plan: UserPlan }) {
  const resetDate = new Date(plan.reset_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })
  return (
    <div className="border border-gray-200 bg-white">
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <p className="text-base font-semibold text-[#111827]">Тариф</p>
          <span className={`text-sm px-2.5 py-0.5 font-medium ${PLAN_COLOR[plan.plan] ?? PLAN_COLOR.free}`}>
            {PLAN_LABEL[plan.plan] ?? plan.plan}
          </span>
        </div>
        {plan.plan === "free" && (
          <a
            href="/#pricing"
            className="text-sm text-violet-600 hover:text-violet-700 font-medium transition-colors"
          >
            Улучшить тариф
          </a>
        )}
      </div>
      <div className="px-6 py-5 space-y-4">
        <UsageBar used={plan.ai_summaries.used} limit={plan.ai_summaries.limit} label="AI-резюме" />
        <UsageBar used={plan.rag_questions.used} limit={plan.rag_questions.limit} label="Вопросы по тендеру" />
        <UsageBar used={plan.companies.used} limit={plan.companies.limit} label="Компании" />
        <p className="text-xs text-gray-400">Счётчики сбрасываются {resetDate}</p>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const router = useRouter()
  const qc = useQueryClient()
  const [innSuggestion, setInnSuggestion] = useState<InnLookupResult | null>(null)
  const [selectedProfileId, setSelectedProfileId] = useState<number | null>(null)
  const [showOnboarding] = useState(() => {
    if (typeof window === "undefined") return false
    return !localStorage.getItem("onboarding_dismissed")
  })
  const [showNewCompanyForm, setShowNewCompanyForm] = useState(false)
  const [newCompanyName, setNewCompanyName] = useState("")

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  const { data: companies = [], isLoading: companiesLoading } = useQuery<CompanyProfile[]>({
    queryKey: ["companies"],
    queryFn: () => profileApi.listCompanies(),
  })

  const { data: billingInfo } = useQuery<UserPlan>({
    queryKey: ["billing"],
    queryFn: () => billingApi.getInfo(),
    staleTime: 60_000,
  })

  const { data: regionOptions = [] } = useQuery<string[]>({
    queryKey: ["regions"],
    queryFn: () => tendersApi.regions(),
  })

  const { data: directionsForCompleteness = [] } = useQuery<CompanyDirection[]>({
    queryKey: ["directions", selectedProfileId],
    queryFn: () => directionsApi.list(selectedProfileId!),
    enabled: !!selectedProfileId,
  })

  // Default to first profile
  useEffect(() => {
    if (companies.length > 0 && !selectedProfileId) {
      setSelectedProfileId(companies[0].id)
    }
  }, [companies, selectedProfileId])

  const selectedCompany = companies.find((c) => c.id === selectedProfileId) ?? null

  const { register, handleSubmit, reset, watch, setValue, formState: { isDirty, isSubmitting } } = useForm<FormValues>()

  // Reset form only when switching profiles (not on every render)
  useEffect(() => {
    if (selectedCompany) reset(toForm(selectedCompany))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProfileId])

  const saveMutation = useMutation({
    mutationFn: (data: FormValues) =>
      selectedProfileId
        ? profileApi.updateCompanyById(selectedProfileId, fromForm(data))
        : Promise.reject("No profile selected"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["companies"] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => profileApi.deleteCompany(id),
    onSuccess: (_, deletedId) => {
      if (selectedProfileId === deletedId) setSelectedProfileId(null)
      qc.invalidateQueries({ queryKey: ["companies"] })
    },
  })

  const createCompanyMutation = useMutation({
    mutationFn: (name: string) => profileApi.createCompany({ name }),
    onSuccess: (newCompany) => {
      const company = newCompany as CompanyProfile
      qc.invalidateQueries({ queryKey: ["companies"] })
      setSelectedProfileId(company.id)
      reset(toForm(company))  // populate form immediately without waiting for refetch
      setShowNewCompanyForm(false)
      setNewCompanyName("")
    },
  })

  const innValue = watch("inn")
  const currentName = watch("name")
  const [innLookupLoading, setInnLookupLoading] = useState(false)
  const [innLookupError, setInnLookupError] = useState<string | null>(null)

  async function handleInnLookup() {
    const val = (innValue ?? "").trim().replace(/\D/g, "")
    if (val.length !== 10 && val.length !== 12) {
      setInnLookupError("ИНН должен содержать 10 или 12 цифр")
      return
    }
    setInnLookupLoading(true)
    setInnLookupError(null)
    try {
      const res = await profileApi.lookupInn(val)
      if (res.data) {
        if (res.data.name) setValue("name", res.data.name, { shouldDirty: true })
        setInnSuggestion(res.data)
      } else {
        setInnLookupError(res.error ?? "Компания не найдена")
      }
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setInnLookupError(msg ?? "Ошибка запроса")
    } finally {
      setInnLookupLoading(false)
    }
  }

  async function handleApplySuggestion(selected: { okved_code: string; name: string }[]) {
    await Promise.all(
      selected.map((d) =>
        directionsApi.create({
          name: d.name,
          description: "",
          okved_codes: [d.okved_code],
          keywords: [],
          exclude_keywords: [],
          regions: [],
          law_types: [],
          procedure_types: [],
          nmck_min: null,
          nmck_max: null,
        }, selectedProfileId ?? undefined)
      )
    )
    qc.invalidateQueries({ queryKey: ["directions", selectedProfileId] })
    setInnSuggestion(null)
  }

  const isChanged = isDirty

  return (
    <div className="flex flex-col h-screen animate-fade-in">
      {/* Header */}
      <div className="h-16 flex items-center justify-between px-6 border-b border-gray-200 shrink-0">
        <h1 className="text-lg font-bold text-[#111827]">Профиль компании</h1>
        {selectedCompany && (
          <button
            onClick={handleSubmit((data) => saveMutation.mutateAsync(data))}
            disabled={!isChanged || isSubmitting}
            className="h-10 px-5 text-base font-medium bg-[#111827] text-white hover:bg-[#1f2937] transition-colors disabled:opacity-40"
          >
            {isSubmitting ? "Сохранение..." : saveMutation.isSuccess ? "Сохранено" : "Сохранить"}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-10 space-y-8">

          {/* Onboarding banner — only when no directions */}
          {showOnboarding && directionsForCompleteness.length === 0 && selectedCompany && (
            <div className="border border-violet-200 bg-violet-50/50 px-6 py-5">
              <p className="text-base font-medium text-[#111827]">
                Создайте направление поиска, чтобы получать персональные рекомендации тендеров
              </p>
              <button
                type="button"
                onClick={() => {
                  const el = document.getElementById("directions-section")
                  el?.scrollIntoView({ behavior: "smooth" })
                }}
                className="mt-3 h-9 px-4 text-sm font-medium bg-[#111827] text-white hover:bg-[#1f2937] transition-colors"
              >
                Создать направление
              </button>
            </div>
          )}

          {/* Plan */}
          {billingInfo && <PlanBlock plan={billingInfo} />}

          {/* Company selector */}
          <div className="border border-gray-200 bg-white">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <p className="text-base font-semibold text-[#111827]">Компании</p>
              <button
                type="button"
                onClick={() => setShowNewCompanyForm((v) => !v)}
                className="flex items-center gap-2 h-9 px-4 text-sm font-medium border border-gray-200 text-gray-700 hover:text-[#111827] hover:border-gray-300 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Добавить компанию
              </button>
            </div>

            <div className="px-6 py-4 space-y-2">
              {companiesLoading ? (
                <p className="text-sm text-gray-500">Загрузка...</p>
              ) : (
                <>
                  {companies.map((company) => (
                    <div
                      key={company.id}
                      onClick={() => { setSelectedProfileId(company.id); setInnSuggestion(null) }}
                      className={`flex items-center gap-3 px-4 py-3 border cursor-pointer transition-colors ${
                        selectedProfileId === company.id
                          ? "border-[#111827] bg-gray-50"
                          : "border-gray-200 hover:border-gray-300 hover:bg-gray-50/50"
                      }`}
                    >
                      <Building2 className="w-4 h-4 text-gray-400 shrink-0" />
                      <span className="flex-1 text-sm font-medium text-[#111827] truncate">
                        {/* Show live form name for selected company, saved name for others */}
                        {company.id === selectedProfileId
                          ? (currentName || company.name || "Без названия")
                          : (company.name || "Без названия")}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          if (confirm(`Удалить компанию «${company.name || "Без названия"}»?`)) {
                            deleteMutation.mutate(company.id)
                          }
                        }}
                        className="p-1 rounded text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}

                  {showNewCompanyForm && (
                    <div className="flex items-center gap-2 mt-3">
                      <input
                        autoFocus
                        className={inputCls + " flex-1"}
                        placeholder="Название новой компании"
                        value={newCompanyName}
                        onChange={(e) => setNewCompanyName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && newCompanyName.trim()) createCompanyMutation.mutate(newCompanyName.trim())
                          if (e.key === "Escape") { setShowNewCompanyForm(false); setNewCompanyName("") }
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => { if (newCompanyName.trim()) createCompanyMutation.mutate(newCompanyName.trim()) }}
                        disabled={!newCompanyName.trim() || createCompanyMutation.isPending}
                        className="h-11 px-4 text-sm font-medium bg-[#111827] text-white hover:bg-[#1f2937] transition-colors disabled:opacity-50"
                      >
                        {createCompanyMutation.isPending ? "..." : "Создать"}
                      </button>
                      <button
                        type="button"
                        onClick={() => { setShowNewCompanyForm(false); setNewCompanyName("") }}
                        className="h-11 px-3 text-sm text-gray-500 hover:text-gray-900 border border-gray-200 hover:border-gray-300 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  )}

                  {companies.length === 0 && !showNewCompanyForm && (
                    <p className="text-sm text-gray-500">Добавьте компанию для начала работы.</p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Company detail (shown when a company is selected) */}
          {selectedCompany && (
            <>
              {/* Profile completeness */}
              <ProfileCompleteness profile={selectedCompany} directions={directionsForCompleteness} />

              {/* Company info card */}
              <div className="border border-gray-200 bg-white">
                <div className="px-6 py-4 border-b border-gray-200">
                  <p className="text-base font-semibold text-[#111827]">Данные компании</p>
                </div>
                <div className="px-6 py-6">
                  <form onSubmit={handleSubmit((data) => saveMutation.mutateAsync(data))}>
                    <div className="space-y-5">
                      <Field label="Название">
                        <input className={inputCls} placeholder="ООО Технологии" autoComplete="off" {...register("name")} />
                      </Field>
                      <Field label="ИНН">
                        <div className="flex gap-2">
                          <input className={inputCls} placeholder="7700000000" autoComplete="off" {...register("inn")} />
                          <button
                            type="button"
                            onClick={handleInnLookup}
                            disabled={innLookupLoading}
                            className="shrink-0 h-11 px-5 text-sm font-medium border border-gray-200 text-gray-700 hover:text-[#111827] hover:border-gray-300 transition-colors disabled:opacity-50 flex items-center gap-2"
                          >
                            {innLookupLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                            Найти
                          </button>
                        </div>
                        {innLookupError && (
                          <p className="text-sm text-red-500 mt-2">{innLookupError}</p>
                        )}
                        {innSuggestion && (
                          <InnSuggestPanel
                            result={innSuggestion}
                            onApply={handleApplySuggestion}
                            onDismiss={() => setInnSuggestion(null)}
                          />
                        )}
                      </Field>
                    </div>
                    {saveMutation.isError && (
                      <p className="text-sm text-red-500 mt-4">Ошибка сохранения</p>
                    )}
                  </form>
                </div>
              </div>


              {/* Won tenders */}
              <WonTendersSection
                profile={selectedCompany}
                onSave={(ids) =>
                  profileApi.updateCompanyById(selectedCompany.id, { won_tender_ids: ids }).then(() => {
                    qc.invalidateQueries({ queryKey: ["companies"] })
                  })
                }
              />

              {/* Directions card */}
              <div id="directions-section" className="border border-gray-200 bg-white">
                <DirectionsSection regionOptions={regionOptions} profileId={selectedProfileId ?? undefined} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
