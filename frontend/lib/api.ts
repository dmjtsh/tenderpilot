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
  finances: string
  red_flags: string[]
  verdict: "go" | "maybe" | "pass"
  verdict_reason: string
  has_docs?: boolean
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

export const tendersApi = {
  list: (page = 1) =>
    client.get("/tenders/", { params: { page } }).then((r) => r.data),

  get: (id: number) =>
    client.get(`/tenders/${id}/`).then((r) => r.data),

  regions: () =>
    client.get("/tenders/regions/").then((r) => r.data.data as string[]),

  getSummary: (id: number) =>
    client.get(`/tenders/${id}/summary/`).then((r) => r.data.data as TenderSummary),
}

// Search
export const searchApi = {
  search: (query: string, filters: { nmck_max?: number; status?: string } = {}) =>
    client
      .post("/search/", { query, limit: 20, ...filters })
      .then((r) => r.data.data as Tender[]),

  match: (limit = 20, directionIds?: number[]) =>
    client
      .get("/search/match/", { params: { limit, ...(directionIds?.length ? { direction_ids: directionIds.join(",") } : {}) } })
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
