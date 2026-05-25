"use client"

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { SlidersHorizontal, X } from "lucide-react"
import type { TenderFilters } from "@/hooks/use-tender-filters"
import { tendersApi, customerApi } from "@/lib/api"
import { FilterDropdown } from "./filter-dropdown"
import { MultiSelectFilter } from "./multi-select-filter"
import { RangeFilter } from "./range-filter"
import { DeadlineFilter } from "./deadline-filter"

const PROCEDURE_OPTIONS = [
  { value: "auction", label: "Аукцион" },
  { value: "contest", label: "Конкурс" },
  { value: "request_quotations", label: "Запрос котировок" },
  { value: "request_proposals", label: "Запрос предложений" },
  { value: "single_source", label: "Единственный поставщик" },
  { value: "other", label: "Иной способ" },
]

const LAW_OPTIONS = [
  { value: "44-ФЗ", label: "44-ФЗ" },
  { value: "223-ФЗ", label: "223-ФЗ" },
  { value: "615-ПП", label: "615-ПП" },
  { value: "b2b", label: "Коммерческие" },
]

const PLATFORM_OPTIONS = [
  { value: "РТС-тендер", label: "РТС-тендер" },
  { value: "Сбербанк-АСТ", label: "Сбербанк-АСТ" },
  { value: "Росэлторг", label: "Росэлторг" },
  { value: "Фабрикант", label: "Фабрикант" },
  { value: "ГПБ", label: "ЭТП ГПБ" },
  { value: "АГЗ РТ", label: "АГЗ РТ" },
  { value: "ТЭК-Торг", label: "ТЭК-Торг" },
  { value: "РАД", label: "РАД" },
  { value: "ЕЭТП", label: "ЕЭТП" },
  { value: "Портал поставщиков", label: "Портал поставщиков" },
  { value: "РТС-МАРКЕТ", label: "РТС-Маркет" },
  { value: "B2B-Center", label: "B2B-Center" },
  { value: "Берез", label: "Берёзка" },
  { value: "ОТС", label: "ОТС" },
  { value: "Бидзаар", label: "Бидзаар" },
  { value: "SberB2B", label: "SberB2B" },
  { value: "Tender.Pro", label: "Tender.Pro" },
  { value: "ЗаказРф", label: "ЗаказРФ" },
  { value: "ONLINECONTRACT", label: "Онлайнконтракт" },
]

interface Props {
  filters: TenderFilters
  setFilter: <K extends keyof TenderFilters>(key: K, value: TenderFilters[K]) => void
  setFilters: (next: TenderFilters) => void
  clearAll: () => void
  activeCount: number
}

export function FilterBar({ filters, setFilter, setFilters, clearAll, activeCount }: Props) {
  const [drawerOpen, setDrawerOpen] = useState(false)

  const { data: regions = [] } = useQuery({
    queryKey: ["regions"],
    queryFn: () => tendersApi.regions(),
    staleTime: 5 * 60 * 1000,
  })

  const regionOptions = regions.map((r: string) => ({ value: r, label: r }))

  const [customerQuery, setCustomerQuery] = useState("")
  const { data: customerResults = [], isFetching: customerLoading } = useQuery({
    queryKey: ["customer-search", customerQuery],
    queryFn: () => customerApi.search(customerQuery),
    enabled: customerQuery.length >= 2,
    staleTime: 30_000,
  })
  const customerOptions = customerResults.map((c: { inn: string; name: string }) => ({
    value: c.name,
    label: c.name,
  }))

  const content = (
    <>
      <FilterDropdown label="Процедура" activeCount={filters.procedure_type.length}>
        <MultiSelectFilter
          options={PROCEDURE_OPTIONS}
          selected={filters.procedure_type}
          onChange={(v) => setFilter("procedure_type", v)}
        />
      </FilterDropdown>

      <FilterDropdown label="Закон" activeCount={filters.law_type.length}>
        <MultiSelectFilter
          options={LAW_OPTIONS}
          selected={filters.law_type}
          onChange={(v) => setFilter("law_type", v)}
        />
      </FilterDropdown>

      <FilterDropdown label="Площадка" activeCount={filters.platforms.length}>
        <MultiSelectFilter
          options={PLATFORM_OPTIONS}
          selected={filters.platforms}
          onChange={(v) => setFilter("platforms", v)}
        />
      </FilterDropdown>

      <FilterDropdown
        label="НМЦК"
        activeCount={filters.nmck_min !== null || filters.nmck_max !== null ? 1 : 0}
      >
        <RangeFilter
          min={filters.nmck_min}
          max={filters.nmck_max}
          onChange={(min, max) => {
            setFilters({ ...filters, nmck_min: min, nmck_max: max })
          }}
        />
      </FilterDropdown>

      <FilterDropdown label="Регион" activeCount={filters.regions.length}>
        <MultiSelectFilter
          options={regionOptions}
          selected={filters.regions}
          onChange={(v) => setFilter("regions", v)}
          searchable
          searchPlaceholder="Найти регион..."
        />
      </FilterDropdown>

      <FilterDropdown
        label="Дедлайн"
        activeCount={filters.deadline_days !== null || filters.deadline_days_min !== null ? 1 : 0}
      >
        <DeadlineFilter
          min={filters.deadline_days_min}
          max={filters.deadline_days}
          onChange={(min, max) => {
            setFilters({ ...filters, deadline_days_min: min, deadline_days: max })
          }}
        />
      </FilterDropdown>

      <FilterDropdown
        label="Заказчик"
        activeCount={filters.customers.length}
        wide
      >
        <MultiSelectFilter
          options={customerOptions}
          selected={filters.customers}
          onChange={(v) => setFilter("customers", v)}
          searchable
          searchPlaceholder="Название или ИНН..."
          onSearch={setCustomerQuery}
          loading={customerLoading}
        />
      </FilterDropdown>
    </>
  )

  return (
    <>
      {/* Desktop */}
      <div className="hidden md:flex items-center gap-2 px-6 py-2.5 border-b border-gray-200 flex-wrap">
        <span className="text-xs text-gray-400 mr-1">Фильтры</span>
        {content}
        {activeCount > 0 && (
          <button
            onClick={clearAll}
            className="inline-flex items-center gap-1 h-8 px-3 text-xs text-gray-500 hover:text-gray-700 ml-auto"
          >
            <X className="w-3.5 h-3.5" />
            Сбросить всё
          </button>
        )}
      </div>

      {/* Mobile trigger */}
      <div className="md:hidden px-4 py-2 border-b border-gray-200">
        <button
          onClick={() => setDrawerOpen(true)}
          className={`inline-flex items-center gap-2 h-9 px-4 text-sm border rounded-md transition-colors ${
            activeCount > 0
              ? "bg-violet-50 border-violet-200 text-violet-700"
              : "border-gray-200 text-gray-600"
          }`}
        >
          <SlidersHorizontal className="w-4 h-4" />
          Фильтры
          {activeCount > 0 && (
            <span className="bg-violet-600 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
              {activeCount}
            </span>
          )}
        </button>
      </div>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/30"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute top-0 right-0 bottom-0 w-[320px] bg-white shadow-xl flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <span className="font-medium text-[#111827]">Фильтры</span>
              <button onClick={() => setDrawerOpen(false)}>
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Процедура</p>
                <MultiSelectFilter
                  options={PROCEDURE_OPTIONS}
                  selected={filters.procedure_type}
                  onChange={(v) => setFilter("procedure_type", v)}
                />
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Закон</p>
                <MultiSelectFilter
                  options={LAW_OPTIONS}
                  selected={filters.law_type}
                  onChange={(v) => setFilter("law_type", v)}
                />
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1.5">НМЦК</p>
                <RangeFilter
                  min={filters.nmck_min}
                  max={filters.nmck_max}
                  onChange={(min, max) => {
                    setFilter("nmck_min", min)
                    setTimeout(() => setFilter("nmck_max", max), 0)
                  }}
                />
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Регион</p>
                <MultiSelectFilter
                  options={regionOptions}
                  selected={filters.regions}
                  onChange={(v) => setFilter("regions", v)}
                  searchable
                  searchPlaceholder="Найти регион..."
                />
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Дедлайн подачи</p>
                <DeadlineFilter
                  min={filters.deadline_days_min}
                  max={filters.deadline_days}
                  onChange={(min, max) => {
                    setFilters({ ...filters, deadline_days_min: min, deadline_days: max })
                  }}
                />
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1.5">Заказчик</p>
                <MultiSelectFilter
                  options={customerOptions}
                  selected={filters.customers}
                  onChange={(v) => setFilter("customers", v)}
                  searchable
                  searchPlaceholder="Название или ИНН..."
                  onSearch={setCustomerQuery}
                  loading={customerLoading}
                />
              </div>
            </div>
            <div className="px-4 py-3 border-t border-gray-200 flex gap-2">
              {activeCount > 0 && (
                <button
                  onClick={clearAll}
                  className="flex-1 h-10 text-sm border border-gray-200 rounded-md text-gray-600 hover:bg-gray-50"
                >
                  Сбросить
                </button>
              )}
              <button
                onClick={() => setDrawerOpen(false)}
                className="flex-1 h-10 text-sm bg-[#111827] text-white rounded-md"
              >
                Применить
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
