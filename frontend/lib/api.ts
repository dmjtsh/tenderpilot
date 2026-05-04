import axios from "axios"
import { getToken, clearTokens } from "./auth"

const API_BASE = "http://localhost:8080/api/v1"

export const client = axios.create({ baseURL: API_BASE })

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401 && getToken()) {
      clearTokens()
      window.location.href = "/login"
    }
    return Promise.reject(error)
  }
)

// Auth
export const authApi = {
  login: (email: string, password: string) =>
    client.post("/users/auth/token/", { email, password }).then((r) => r.data),

  register: (data: { email: string; password: string; password2: string; first_name?: string }) =>
    client.post("/users/register/", data).then((r) => r.data.data),
}

// Tenders
export interface TenderSummary {
  essence: string
  requirements: string[]
  days_left: number | null
  urgency: "low" | "medium" | "high" | "critical"
  execution_period?: string | null
  finances: string
  financials?: {
    bid_security_rub: number | null
    contract_security_pct: number | null
    contract_security_note: string | null
  }
  red_flags: string[]
  verdict: "go" | "maybe" | "pass"
  verdict_reason: string
  has_docs?: boolean
  tender_type?: string
}

export interface Tender {
  id: number
  number: string
  title: string
  nmck: number | null
  customer_name?: string
  customer?: { id: number; inn: string; name: string; full_name: string; region: string }
  region: string
  okpd_codes: string[]
  published_at: string | null
  deadline_at: string | null
  auction_date: string | null
  status: string
  law_type: string
  procedure_type?: string
  trading_platform: string
  trading_platform_url: string
  bid_security_amount: number | null
  bid_security_required: boolean | null
  contract_security_amount: number | null
  contract_security_percent: number | null
  source_url: string
  ai_summary?: string
  score?: number
  matched_direction?: string | null
}

export interface TenderDoc {
  id: number
  filename: string
  file_type: string
  parse_status: "pending" | "processing" | "done" | "failed" | "skipped" | "cleaned"
  file_size: number
  is_scanned: boolean
  content_priority: number
  archive_name?: string
}

export interface TenderQASource {
  filename: string
  chunk_index: number
  text: string
  document_id: number | null
}

export interface TenderQAResponse {
  answer: string | null
  has_docs: boolean
  sources: TenderQASource[]
  needs_reindex?: boolean
}

export const tendersApi = {
  list: (page = 1, filters: Record<string, string> = {}) =>
    client.get("/tenders/", { params: { page, ...filters } }).then((r) => r.data),

  get: (id: number) =>
    client.get(`/tenders/${id}/`).then((r) => r.data),

  regions: () =>
    client.get("/tenders/regions/").then((r) => r.data.data as string[]),

  getSummary: (id: number, refresh = false) =>
    client.get(`/tenders/${id}/summary/`, { params: refresh ? { refresh: "true" } : {} }).then((r) => r.data.data as TenderSummary),

  getDocs: (id: number) =>
    client.get(`/tenders/${id}/docs/`).then((r) => r.data.data as TenderDoc[]),

  downloadDocs: (id: number) =>
    client.post(`/tenders/${id}/download-docs/`).then((r) => r.data.data),

  askQuestion: (id: number, question: string) =>
    client.post(`/tenders/${id}/ask/`, { question }).then((r) => r.data.data as TenderQAResponse),

  reindexDocs: (id: number) =>
    client.post(`/tenders/${id}/reindex-docs/`).then((r) => r.data.data),
}

// Search
export const searchApi = {
  search: (query: string, filters: Record<string, unknown> = {}) =>
    client
      .post("/search/", { query, limit: 20, ...filters })
      .then((r) => r.data.data as Tender[]),

  match: (limit = 20, directionIds?: number[], filters: Record<string, string> = {}) =>
    client
      .get("/search/match/", {
        params: {
          limit,
          ...(directionIds?.length ? { direction_ids: directionIds.join(",") } : {}),
          ...filters,
        },
      })
      .then((r) => r.data as { data: Tender[]; error: string | null }),
}

// Profile
export interface CompanyProfile {
  id: number
  name: string
  inn: string
  description: string
  okved_codes: string[]
  regions: string[]
  keywords: string[]
}

export interface CompanyDirection {
  id: number
  name: string
  okved_codes: string[]
  keywords: string[]
  regions: string[]
  nmck_min: number | null
  nmck_max: number | null
  law_types: string[]
  procedure_types: string[]
  vector_updated_at: string | null
  created_at: string
}

export interface InnLookupResult {
  name: string
  full_name: string
  inn: string
  region: string
  okved_main: string
  okved_list: string[]
  suggested_directions: { okved_code: string; name: string }[]
}

export const profileApi = {
  getMe: () => client.get("/users/me/").then((r) => r.data),
  getCompany: () => client.get("/users/me/company/").then((r) => r.data),
  updateCompany: (data: Partial<CompanyProfile>) =>
    client.patch("/users/me/company/", data).then((r) => r.data),
  lookupInn: (inn: string) =>
    client
      .post("/users/lookup-inn/", { inn })
      .then((r) => r.data as { data: InnLookupResult | null; error: string | null }),
}

export const okvedApi = {
  search: (q: string) =>
    client
      .get("/tenders/okved/", { params: { q } })
      .then((r) => r.data.data as { code: string; name: string }[]),
}

// Pipeline
export type PipelineStatus = "studying" | "preparing" | "submitted" | "won" | "lost"

export interface TenderPipelineEntry {
  id: number
  tender: number
  status: PipelineStatus
  notes: string
  tender_title: string
  tender_number: string
  tender_nmck: number | null
  tender_region: string
  tender_deadline_at: string | null
  tender_customer_name: string
  created_at: string
  updated_at: string
}

export interface PipelineSummary {
  in_work_count: number
  in_work_sum: number
  won_count: number
  won_sum: number
  lost_count: number
  lost_sum: number
}

export const pipelineApi = {
  list: () =>
    client.get("/tenders/pipeline/").then((r) => (r.data.results ?? r.data) as TenderPipelineEntry[]),
  create: (tender: number, status: PipelineStatus) =>
    client.post("/tenders/pipeline/", { tender, status }).then((r) => r.data as TenderPipelineEntry),
  update: (id: number, data: { status?: PipelineStatus; notes?: string }) =>
    client.patch(`/tenders/pipeline/${id}/`, data).then((r) => r.data as TenderPipelineEntry),
  remove: (id: number) =>
    client.delete(`/tenders/pipeline/${id}/`),
  summary: () =>
    client.get("/tenders/pipeline/summary/").then((r) => r.data.data as PipelineSummary),
  byTender: (tenderId: number) =>
    client.get(`/tenders/pipeline/by-tender/${tenderId}/`).then((r) => r.data.data as TenderPipelineEntry | null),
}

export const directionsApi = {
  list: () =>
    client.get("/users/me/directions/").then((r) => (r.data.results ?? r.data) as CompanyDirection[]),
  create: (data: Omit<CompanyDirection, "id" | "vector_updated_at" | "created_at">) =>
    client.post("/users/me/directions/", data).then((r) => r.data as CompanyDirection),
  update: (id: number, data: Partial<CompanyDirection>) =>
    client.patch(`/users/me/directions/${id}/`, data).then((r) => r.data as CompanyDirection),
  remove: (id: number) =>
    client.delete(`/users/me/directions/${id}/`),
}
