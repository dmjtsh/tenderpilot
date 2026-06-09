"use client"

import { useSearchParams, useRouter, usePathname } from "next/navigation"
import { useCallback, useMemo, useRef } from "react"

export type RegionMode = "only" | "boost"

export interface TenderFilters {
  procedure_type: string[]
  law_type: string[]
  platforms: string[]
  nmck_min: number | null
  nmck_max: number | null
  regions: string[]
  region_mode: RegionMode
  deadline_days: number | null
  deadline_days_min: number | null
  okpd: string[]
  customers: string[]
  industries: string[]
}

export const EMPTY_FILTERS: TenderFilters = {
  procedure_type: [],
  law_type: [],
  platforms: [],
  nmck_min: null,
  nmck_max: null,
  regions: [],
  region_mode: "only",
  deadline_days: null,
  deadline_days_min: null,
  okpd: [],
  customers: [],
  industries: [],
}

function parseFiltersFromParams(sp: URLSearchParams): TenderFilters {
  const csv = (key: string) => {
    const v = sp.get(key)
    return v ? v.split(",").filter(Boolean) : []
  }
  const num = (key: string) => {
    const v = sp.get(key)
    return v ? Number(v) : null
  }
  return {
    procedure_type: csv("procedure_type"),
    law_type: csv("law_type"),
    platforms: csv("platform"),
    nmck_min: num("nmck_min"),
    nmck_max: num("nmck_max"),
    regions: csv("region"),
    region_mode: (sp.get("region_mode") === "boost" ? "boost" : "only") as RegionMode,
    deadline_days: num("deadline_days"),
    deadline_days_min: num("deadline_days_min"),
    okpd: csv("okpd"),
    customers: csv("customer"),
    industries: csv("industry"),
  }
}

export type Tab = "all" | "match"

export function saveFiltersToSession(tab: Tab, filters: TenderFilters): void {
  if (typeof window === "undefined") return
  sessionStorage.setItem(`tender_filters_${tab}`, JSON.stringify(filters))
}

export function loadFiltersFromSession(tab: Tab): TenderFilters | null {
  if (typeof window === "undefined") return null
  const raw = sessionStorage.getItem(`tender_filters_${tab}`)
  if (!raw) return null
  try {
    return JSON.parse(raw) as TenderFilters
  } catch {
    return null
  }
}

export function filtersToParams(filters: TenderFilters): Record<string, string> {
  const p: Record<string, string> = {}
  if (filters.procedure_type.length) p.procedure_type = filters.procedure_type.join(",")
  if (filters.law_type.length) p.law_type = filters.law_type.join(",")
  if (filters.platforms.length) p.platform = filters.platforms.join(",")
  if (filters.nmck_min !== null) p.nmck_min = String(filters.nmck_min)
  if (filters.nmck_max !== null) p.nmck_max = String(filters.nmck_max)
  if (filters.regions.length) p.region = filters.regions.join(",")
  if (filters.region_mode === "boost") p.region_mode = "boost"
  if (filters.deadline_days !== null) p.deadline_days = String(filters.deadline_days)
  if (filters.deadline_days_min !== null) p.deadline_days_min = String(filters.deadline_days_min)
  if (filters.okpd.length) p.okpd = filters.okpd.join(",")
  if (filters.customers.length) p.customer = filters.customers.join(",")
  if (filters.industries.length) p.industry = filters.industries.join(",")
  return p
}

export function filtersToApiParams(filters: TenderFilters): Record<string, string> {
  return filtersToParams(filters)
}

export function filtersToSearchBody(filters: TenderFilters): Record<string, unknown> {
  const body: Record<string, unknown> = {}
  if (filters.procedure_type.length) body.procedure_type = filters.procedure_type
  if (filters.law_type.length) body.law_type = filters.law_type
  if (filters.platforms.length) body.platform = filters.platforms
  if (filters.nmck_min !== null) body.nmck_min = filters.nmck_min
  if (filters.nmck_max !== null) body.nmck_max = filters.nmck_max
  if (filters.regions.length) body.regions = filters.regions
  if (filters.deadline_days !== null) body.deadline_days = filters.deadline_days
  if (filters.deadline_days_min !== null) body.deadline_days_min = filters.deadline_days_min
  if (filters.okpd.length) body.okpd = filters.okpd
  if (filters.customers.length) body.customer = filters.customers.join(",")
  if (filters.industries.length) body.industry = filters.industries
  return body
}

export function useTenderFilters(tab?: Tab) {
  const searchParams = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()

  const filters = useMemo(() => parseFiltersFromParams(searchParams), [searchParams])

  const filtersRef = useRef(filters)
  filtersRef.current = filters

  const setFilters = useCallback(
    (next: TenderFilters) => {
      filtersRef.current = next
      const params = new URLSearchParams(searchParams.toString())
      const FILTER_KEYS = ["procedure_type", "law_type", "platform", "nmck_min", "nmck_max", "region", "region_mode", "deadline_days", "deadline_days_min", "okpd", "customer", "industry"]
      FILTER_KEYS.forEach((k) => params.delete(k))
      const fp = filtersToParams(next)
      Object.entries(fp).forEach(([k, v]) => params.set(k, v))
      router.replace(`${pathname}?${params.toString()}`, { scroll: false })
      if (tab) saveFiltersToSession(tab, next)
    },
    [searchParams, router, pathname, tab]
  )

  const setFilter = useCallback(
    <K extends keyof TenderFilters>(key: K, value: TenderFilters[K]) => {
      setFilters({ ...filtersRef.current, [key]: value })
    },
    [setFilters]
  )

  const clearAll = useCallback(() => setFilters(EMPTY_FILTERS), [setFilters])

  const activeCount = useMemo(() => {
    let c = 0
    if (filters.procedure_type.length) c++
    if (filters.law_type.length) c++
    if (filters.platforms.length) c++
    if (filters.nmck_min !== null || filters.nmck_max !== null) c++
    if (filters.regions.length) c++
    if (filters.deadline_days !== null || filters.deadline_days_min !== null) c++
    if (filters.okpd.length) c++
    if (filters.customers.length) c++
    if (filters.industries.length) c++
    return c
  }, [filters])

  const hasFilters = activeCount > 0

  return { filters, setFilter, setFilters, clearAll, activeCount, hasFilters }
}
