"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { isAuthenticated } from "@/lib/auth"
import { profileApi, directionsApi, tendersApi, type CompanyProfile, type CompanyDirection, type InnLookupResult } from "@/lib/api"
import { ChevronDown, Search, X, Plus, Trash2, Loader2, Sparkles } from "lucide-react"
import { OkvedCombobox } from "@/components/okved-combobox"

type FormValues = {
  name: string
  inn: string
  description: string
}

function toForm(p: CompanyProfile): FormValues {
  return {
    name: p.name ?? "",
    inn: p.inn ?? "",
    description: p.description ?? "",
  }
}

function fromForm(f: FormValues): Partial<CompanyProfile> {
  return {
    name: f.name,
    inn: f.inn,
    description: f.description,
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
  { label: "до 1 млн", min: null, max: 1_000_000 },
  { label: "1–10 млн", min: 1_000_000, max: 10_000_000 },
  { label: "10–50 млн", min: 10_000_000, max: 50_000_000 },
  { label: "50–200 млн", min: 50_000_000, max: 200_000_000 },
  { label: "свыше 200 млн", min: 200_000_000, max: null },
  { label: "своё", min: -1, max: -1 },
] as const

const LAW_TYPES = ["44-ФЗ", "223-ФЗ", "615-ПП"] as const

// ─── DirectionCard ────────────────────────────────────────────────────────────

function DirectionCard({
  direction,
  regionOptions,
  onDelete,
}: {
  direction: CompanyDirection
  regionOptions: string[]
  onDelete: () => void
}) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(!direction.vector_updated_at)

  const [name, setName] = useState(direction.name)
  const [okvedCodes, setOkvedCodes] = useState<string[]>(direction.okved_codes ?? [])
  const [keywords, setKeywords] = useState((direction.keywords ?? []).join(", "))
  const [regions, setRegions] = useState<string[]>(direction.regions ?? [])
  const [lawTypes, setLawTypes] = useState<string[]>(direction.law_types ?? [])
  const [nmckPreset, setNmckPreset] = useState(() => {
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
        okved_codes: okvedCodes,
        keywords: split(keywords),
        regions,
        law_types: lawTypes,
        nmck_min,
        nmck_max,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["directions"] })
      setExpanded(false)
    },
  })

  const isIndexing = !direction.vector_updated_at

  return (
    <div className="border border-border/60 rounded-lg overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-secondary/30 transition-colors"
        onClick={() => setExpanded((e) => !e)}
      >
        <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground shrink-0 transition-transform ${expanded ? "rotate-180" : ""}`} />
        <span className="flex-1 text-sm font-medium text-foreground/90">{name || "Новое направление"}</span>
        {isIndexing ? (
          <span className="flex items-center gap-1.5 text-[10px] text-amber-400/80">
            <Loader2 className="w-3 h-3 animate-spin" />
            индексируется
          </span>
        ) : (
          <span className="text-[10px] text-emerald-400/70">● активно</span>
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
        <div className="px-4 pb-4 pt-1 space-y-4 border-t border-border/40">
          {/* Name */}
          <div>
            <p className="text-xs text-muted-foreground mb-1.5">Название направления</p>
            <input
              className={inputCls}
              placeholder="Кровельные работы"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          {/* OKVED */}
          <div>
            <p className="text-xs text-muted-foreground mb-1.5">ОКВЭД коды</p>
            <OkvedCombobox value={okvedCodes} onChange={setOkvedCodes} />
          </div>

          {/* Keywords */}
          <div>
            <p className="text-xs text-muted-foreground mb-1.5">Ключевые слова <span className="text-muted-foreground/50">(через запятую)</span></p>
            <input
              className={inputCls}
              placeholder="кровля, кровельные работы"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
            />
          </div>

          {/* Regions */}
          <div>
            <p className="text-xs text-muted-foreground mb-1.5">Регионы</p>
            <RegionSelect value={regions} onChange={setRegions} options={regionOptions} />
          </div>

          {/* NMC */}
          <div>
            <p className="text-xs text-muted-foreground mb-1.5">НМЦК</p>
            <div className="flex flex-wrap gap-1.5">
              {NMCK_PRESETS.map((preset, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setNmckPreset(idx)}
                  className={`h-7 px-2.5 text-xs rounded-md border transition-colors ${
                    nmckPreset === idx
                      ? "bg-primary/15 border-primary/40 text-primary"
                      : "border-border/60 text-muted-foreground hover:border-border hover:text-foreground"
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
            <p className="text-xs text-muted-foreground mb-1.5">Типы закупок</p>
            <div className="flex gap-3">
              {LAW_TYPES.map((lt) => (
                <label key={lt} className="flex items-center gap-1.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={lawTypes.includes(lt)}
                    onChange={() =>
                      setLawTypes((prev) =>
                        prev.includes(lt) ? prev.filter((x) => x !== lt) : [...prev, lt]
                      )
                    }
                    className="w-3.5 h-3.5 accent-primary"
                  />
                  <span className="text-xs text-foreground/80 font-mono">{lt}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
              className="h-7 px-3 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
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

function DirectionsSection({ regionOptions }: { regionOptions: string[] }) {
  const qc = useQueryClient()

  const { data: directions = [], isPending, isFetching } = useQuery<CompanyDirection[]>({
    queryKey: ["directions"],
    queryFn: () => directionsApi.list(),
  })

  const createMutation = useMutation({
    mutationFn: () =>
      directionsApi.create({
        name: "Новое направление",
        okved_codes: [],
        keywords: [],
        regions: [],
        law_types: [],
        nmck_min: null,
        nmck_max: null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["directions"] }),
    onError: (e: unknown) => console.error("create direction failed:", e),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => directionsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["directions"] }),
  })

  const isLoading = isPending && isFetching

  return (
    <div className="py-5 border-b border-border/50 last:border-0">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-muted-foreground uppercase tracking-wide">Направления поиска</p>
        <button
          type="button"
          onClick={() => createMutation.mutate()}
          disabled={createMutation.isPending}
          className="flex items-center gap-1 h-6 px-2 text-xs rounded-md border border-border/60 text-muted-foreground hover:text-foreground hover:border-border transition-colors disabled:opacity-50"
        >
          <Plus className="w-3 h-3" />
          Добавить
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Загрузка...</p>
      ) : directions.length === 0 ? (
        <p className="text-xs text-muted-foreground/60">
          Добавьте направления чтобы настроить точный поиск с фильтрами по НМЦ и типу закона.
          HyDE-вектор строится автоматически через ~30 секунд после сохранения.
        </p>
      ) : (
        <div className="space-y-2">
          {directions.map((d) => (
            <DirectionCard
              key={d.id}
              direction={d}
              regionOptions={regionOptions}
              onDelete={() => deleteMutation.mutate(d.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Page ────────────────────────────────────────────────────────────────────

const inputCls = "w-full h-8 rounded-md bg-secondary border border-border px-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors"
const textareaCls = "w-full rounded-md bg-secondary border border-border px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring focus:border-ring transition-colors resize-none"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="py-5 border-b border-border/50 last:border-0">
      <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">{title}</p>
      {children}
    </div>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-4 items-start mb-3 last:mb-0">
      <div className="pt-1.5">
        <p className="text-sm text-foreground/80">{label}</p>
        {hint && <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>}
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
    <div className="mt-4 rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-3.5 h-3.5 text-primary shrink-0" />
        <p className="text-xs font-medium text-foreground">
          Найдено: <span className="text-primary">{result.name}</span>
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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function ProfilePage() {
  const router = useRouter()
  const qc = useQueryClient()
  const [innSuggestion, setInnSuggestion] = useState<InnLookupResult | null>(null)

  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login")
  }, [router])

  const { data: company, isLoading } = useQuery<CompanyProfile>({
    queryKey: ["company"],
    queryFn: () => profileApi.getCompany(),
  })

  const { data: regionOptions = [] } = useQuery<string[]>({
    queryKey: ["regions"],
    queryFn: () => tendersApi.regions(),
  })

  const { register, handleSubmit, reset, watch, setValue, formState: { isDirty, isSubmitting } } = useForm<FormValues>()

  useEffect(() => {
    if (company) reset(toForm(company))
  }, [company, reset])

  const mutation = useMutation({
    mutationFn: (data: FormValues) =>
      profileApi.updateCompany(fromForm(data)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["company"] }),
  })

  const isChanged = isDirty

  const innValue = watch("inn")
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
          okved_codes: [d.okved_code],
          keywords: [],
          regions: [],
          law_types: [],
          nmck_min: null,
          nmck_max: null,
        })
      )
    )
    qc.invalidateQueries({ queryKey: ["directions"] })
    setInnSuggestion(null)
  }

  return (
    <div className="flex flex-col h-screen">
      <div className="h-[52px] flex items-center justify-between px-6 border-b border-border shrink-0">
        <h1 className="text-sm font-medium">Профиль компании</h1>
        {!isLoading && (
          <button
            onClick={handleSubmit((data) => mutation.mutateAsync(data))}
            disabled={!isChanged || isSubmitting}
            className="h-7 px-3 text-xs font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40"
          >
            {isSubmitting ? "Сохранение..." : mutation.isSuccess ? "Сохранено" : "Сохранить"}
          </button>
        )}
      </div>

      <div className="flex-1 overflow-auto">
        <div className="max-w-2xl mx-auto px-6 py-8">
          {isLoading ? (
            <p className="text-xs text-muted-foreground">Загрузка...</p>
          ) : (
            <form onSubmit={handleSubmit((data) => mutation.mutateAsync(data))}>
              <Section title="Компания">
                <Field label="Название">
                  <input className={inputCls} placeholder="ООО Технологии" {...register("name")} />
                </Field>
                <Field label="ИНН">
                  <div className="flex gap-2">
                    <input className={inputCls} placeholder="7700000000" {...register("inn")} />
                    <button
                      type="button"
                      onClick={handleInnLookup}
                      disabled={innLookupLoading}
                      className="shrink-0 h-8 px-3 text-xs rounded-md border border-border/60 text-muted-foreground hover:text-foreground hover:border-border transition-colors disabled:opacity-50 flex items-center gap-1.5"
                    >
                      {innLookupLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
                      Найти
                    </button>
                  </div>
                  {innLookupError && (
                    <p className="text-xs text-destructive mt-1.5">{innLookupError}</p>
                  )}
                  {innSuggestion && (
                    <InnSuggestPanel
                      result={innSuggestion}
                      onApply={handleApplySuggestion}
                      onDismiss={() => setInnSuggestion(null)}
                    />
                  )}
                </Field>
              </Section>

              <Section title="Описание деятельности">
                <textarea
                  className={textareaCls}
                  rows={4}
                  placeholder="Разработка и поставка медицинского оборудования, ИТ-решений..."
                  {...register("description")}
                />
              </Section>

              {mutation.isError && (
                <p className="text-xs text-destructive mt-2">Ошибка сохранения</p>
              )}
            </form>
          )}

          {!isLoading && (
            <DirectionsSection regionOptions={regionOptions} />
          )}
        </div>
      </div>
    </div>
  )
}
