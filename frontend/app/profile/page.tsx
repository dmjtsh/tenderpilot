"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { isAuthenticated } from "@/lib/auth"
import { profileApi, tendersApi, type CompanyProfile } from "@/lib/api"
import { ChevronDown, Search, X } from "lucide-react"

type FormValues = {
  name: string
  inn: string
  description: string
  okved_codes: string
  keywords: string
}

function toForm(p: CompanyProfile): FormValues {
  return {
    name: p.name ?? "",
    inn: p.inn ?? "",
    description: p.description ?? "",
    okved_codes: (p.okved_codes ?? []).join(", "),
    keywords: (p.keywords ?? []).join(", "),
  }
}

function fromForm(f: FormValues, regions: string[]): Partial<CompanyProfile> {
  const split = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean)
  return {
    name: f.name,
    inn: f.inn,
    description: f.description,
    okved_codes: split(f.okved_codes),
    keywords: split(f.keywords),
    regions,
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
          {/* Search */}
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

          {/* Options */}
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

export default function ProfilePage() {
  const router = useRouter()
  const qc = useQueryClient()
  const [selectedRegions, setSelectedRegions] = useState<string[]>([])

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

  const { register, handleSubmit, reset, formState: { isDirty, isSubmitting } } = useForm<FormValues>()

  useEffect(() => {
    if (company) {
      reset(toForm(company))
      setSelectedRegions(company.regions ?? [])
    }
  }, [company, reset])

  const mutation = useMutation({
    mutationFn: (data: FormValues) =>
      profileApi.updateCompany(fromForm(data, selectedRegions)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["company"] }),
  })

  const isChanged = isDirty || (company ? JSON.stringify(selectedRegions) !== JSON.stringify(company.regions ?? []) : false)

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
                  <input className={inputCls} placeholder="7700000000" {...register("inn")} />
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

              <Section title="Параметры поиска тендеров">
                <Field label="ОКВЭД коды" hint="через запятую">
                  <input className={inputCls} placeholder="72.19, 62.01, 26.51" {...register("okved_codes")} />
                </Field>
                <Field label="Ключевые слова" hint="через запятую">
                  <input className={inputCls} placeholder="медицинское оборудование, ИТ" {...register("keywords")} />
                </Field>
                <Field
                  label="Регионы"
                  hint={regionOptions.length === 0 ? "нет данных" : `${regionOptions.length} доступно`}
                >
                  {regionOptions.length > 0 ? (
                    <RegionSelect
                      value={selectedRegions}
                      onChange={setSelectedRegions}
                      options={regionOptions}
                    />
                  ) : (
                    <p className="text-xs text-muted-foreground pt-2">
                      Регионы появятся после загрузки тендеров с детализацией
                    </p>
                  )}
                </Field>
              </Section>

              {mutation.isError && (
                <p className="text-xs text-destructive mt-2">Ошибка сохранения</p>
              )}
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
