import axios from "axios"
import { getToken, clearTokens } from "./auth"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080/api/v1"

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
  version: number
  customer_analysis: {
    name: string
    inn: string
    region: string
    okved_main: string
    tender_count: number
    total_volume: number
    notes: string[]
  }
  work_description: {
    essence: string
    payment_terms: string | null
    execution_period: string | null
    experience_requirements: string[]
    deadline_info: string | null
  }
  key_risks: {
    certifications: string[]
    financial_risks: string[]
    technical_risks: string[]
    unusual_conditions: string[]
  }
  required_documents: {
    mandatory: string[]
    optional: string[]
    special_forms: string[]
  }
  verdict: "go" | "maybe" | "pass"
  verdict_reason: string
  tender_type?: string
  has_docs?: boolean
  days_left: number | null
  urgency: "low" | "medium" | "high" | "critical"
}

export interface TenderSummaryV2 {
  version: "v2"
  generated_at?: string
  general: {
    title: string
    customer_name: string | null
    customer_inn: string | null
    law_type: string | null
    nmck: number | null
    region: string | null
  }
  customer_analysis: {
    name: string
    inn: string | null
    region: string | null
    org_type: string | null
    industry: string | null
    founded_date: string | null
    financials: { revenue_rub: number | null; profit_rub: number | null; employees_count: number | null; revenue_year: number | null }
    procurement_history: { total_purchases: number | null; total_amount_rub: number | null; avg_contract_rub: number | null }
    risk_indicators: { arbitration_count: number | null; fssp_count: number | null; licenses_count: number | null; red_flags: string[] }
    notes: string[]
    reliability: string | null
  } | null
  work_description: {
    subject: string
    tender_type: string | null
    scope: { main_activities: string[]; deliverables: string[]; volume_metrics: { metric: string; value: string }[] }
    location: { address: string | null; region: string | null }
    technical_specs: { standards: string[]; materials: string[]; equipment: string[]; software: string[] }
    acceptance: { procedure: string | null; review_days: number | null; warranty_months: number | null; support_after_delivery: string | null }
    subcontracting: { allowed: boolean | null; max_pct: number | null; restrictions: string | null }
  } | null
  financial: {
    advance: { has_advance: boolean; amount_rub: number | null; amount_pct: number | null; description: string | null }
    payment: { structure: string | null; count: number | null; term_days: number | null; term_days_type: string | null; fixed_price: boolean | null; schedule_description: string | null }
    funding_source: string | null
    securities: { bid_amount_rub: number | null; bid_pct: number | null; contract_amount_rub: number | null; contract_pct: number | null; contract_form: string | null; return_term_days: number | null }
    penalties: { delay_pen_formula: string | null; delay_pen_base: string | null; fixed_fine_rub: number | null; fixed_fine_basis: string | null }
    antidumping: { applicable: boolean; threshold_pct: number | null; multiplier: number | null }
    cash_flow_note: string | null
  } | null
  timeline: {
    total_duration: { days: number | null; day_type: string | null; description: string | null }
    stages: { number: number; name: string; duration_days: number | null; start_date: string | null; end_date: string | null; deliverables: string[] }[]
    key_dates: { submission_deadline: string | null; auction_date: string | null; contract_sign_deadline_days: number | null; warranty_months: number | null }
    urgency_note: string | null
  } | null
  requirements: {
    eligibility: {
      licenses: { name: string; issuer: string | null; mandatory: boolean }[]
      sro: { required: boolean; type: string | null }
      experience: { min_contracts: number | null; min_amount_rub: number | null; years: number | null; description: string | null }
      staff: { role: string; count: number | null; qualifications: string | null }[]
      financial: { min_revenue_rub: number | null; no_bankruptcy: boolean | null; no_tax_debt: boolean | null }
      other: string[]
    }
    submission: { documents: { name: string; mandatory: boolean }[]; forms: string[]; electronic_signature: boolean | null }
    evaluation_criteria: { name: string; weight_pct: number | null; description: string | null }[]
    restrictions: { smp_only: boolean | null; national_regime: boolean | null; region_restriction: string | null; other: string[] }
    notes: string | null
  } | null
  risks: {
    certification_risks: { risk: string; severity: string }[]
    financial_risks: { risk: string; severity: string }[]
    technical_risks: { risk: string; severity: string }[]
    legal_risks: { risk: string; severity: string }[]
    timeline_risks: { risk: string; severity: string }[]
    unusual_conditions: string[]
    overall_risk: string | null
    risk_summary: string | null
  } | null
}

export type AnySummary = TenderSummary | TenderSummaryV2

export function isV2Summary(s: AnySummary): s is TenderSummaryV2 {
  return s?.version === "v2"
}

export interface SummaryExperimentResult {
  id: number
  strategy: string
  model: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  duration_ms: number
  was_truncated: boolean
  truncated_reason: string
  original_total_tokens: number
  result: AnySummary
  created_at: string
}

export interface ExperimentVariant {
  label: string
  name: string
  strategy: string
  model: string
  prompt_template: string
  params?: Record<string, unknown>
}

export interface ExperimentSummary {
  id: number
  name: string
  status: "draft" | "running" | "completed"
  variants: ExperimentVariant[]
  completed_at: string | null
}

export interface ExperimentRun {
  id: number
  variant_label: string
  variant_name: string
  strategy: string
  model: string
  actual_model?: string
  input_tokens: number
  output_tokens: number
  cost_usd: number
  duration_ms: number
  was_truncated: boolean
  truncated_reason: string
  result: AnySummary
  created_at: string
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
  source?: "eis" | "other"
  ai_summary?: string
  score?: number
  score_label?: string
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
    client.get(`/tenders/${id}/summary/`, { params: refresh ? { refresh: "true" } : {} }).then((r) => r.data.data as AnySummary),

  getDocs: (id: number) =>
    client.get(`/tenders/${id}/docs/`).then((r) => r.data.data as TenderDoc[]),

  downloadDocs: (id: number) =>
    client.post(`/tenders/${id}/download-docs/`).then((r) => r.data.data),

  askQuestion: (id: number, question: string) =>
    client.post(`/tenders/${id}/chat/v1/`, { question }).then((r) => r.data.data as TenderQAResponse),

  reindexDocs: (id: number) =>
    client.post(`/tenders/${id}/reindex-docs/`).then((r) => r.data.data),

  runExperiment: (id: number, strategy: "rag" | "full") =>
    client.post(`/tenders/${id}/summary/experiment/`, { strategy }).then((r) => r.data.data as SummaryExperimentResult),

  getExperiments: (id: number) =>
    client.get(`/tenders/${id}/summary/experiments/`).then((r) => r.data.data as SummaryExperimentResult[]),
}

// Search
export const searchApi = {
  search: (query: string, filters: Record<string, unknown> = {}) =>
    client
      .post("/search/", { query, limit: 20, ...filters })
      .then((r) => r.data.data as Tender[]),

  match: (limit = 20, directionIds?: number[], filters: Record<string, string> = {}, profileId?: number, page = 1, sort = "score") =>
    client
      .get("/search/match/", {
        params: {
          limit,
          page,
          sort,
          ...(directionIds?.length ? { direction_ids: directionIds.join(",") } : {}),
          ...(profileId ? { profile_id: profileId } : {}),
          ...filters,
        },
      })
      .then((r) => r.data as { data: Tender[]; has_more: boolean; error: string | null }),
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
  description: string
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
  listCompanies: () =>
    client.get("/users/me/companies/").then((r) => (r.data.results ?? r.data) as CompanyProfile[]),
  createCompany: (data: Partial<CompanyProfile>) =>
    client.post("/users/me/companies/", data).then((r) => r.data as CompanyProfile),
  updateCompanyById: (id: number, data: Partial<CompanyProfile>) =>
    client.patch(`/users/me/companies/${id}/`, data).then((r) => r.data as CompanyProfile),
  deleteCompany: (id: number) =>
    client.delete(`/users/me/companies/${id}/`),
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

export const customerApi = {
  search: (q: string) =>
    client
      .get("/tenders/customers/", { params: { q } })
      .then((r) => r.data.data as { inn: string; name: string }[]),
}

// Pipeline
export type PipelineStatus = "studying" | "preparing" | "submitted" | "won" | "lost"

export interface TenderPipelineEntry {
  id: number
  tender: number
  profile: number | null
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
  list: (profileId?: number | null) => {
    const params = profileId ? `?profile_id=${profileId}` : ""
    return client.get(`/tenders/pipeline/${params}`).then((r) => (r.data.results ?? r.data) as TenderPipelineEntry[])
  },
  create: (tender: number, status: PipelineStatus, profileId?: number | null) =>
    client.post("/tenders/pipeline/", { tender, status, profile: profileId ?? null }).then((r) => r.data as TenderPipelineEntry),
  update: (id: number, data: { status?: PipelineStatus; notes?: string }) =>
    client.patch(`/tenders/pipeline/${id}/`, data).then((r) => r.data as TenderPipelineEntry),
  remove: (id: number) =>
    client.delete(`/tenders/pipeline/${id}/`),
  summary: (profileId?: number | null) => {
    const params = profileId ? `?profile_id=${profileId}` : ""
    return client.get(`/tenders/pipeline/summary/${params}`).then((r) => r.data.data as PipelineSummary)
  },
  byTender: (tenderId: number) =>
    client.get(`/tenders/pipeline/by-tender/${tenderId}/`).then((r) => r.data.data as TenderPipelineEntry | null),
}

export const directionsApi = {
  list: (profileId?: number) =>
    client.get(
      profileId ? `/users/me/companies/${profileId}/directions/` : "/users/me/directions/",
    ).then((r) => (r.data.results ?? r.data) as CompanyDirection[]),
  create: (data: Omit<CompanyDirection, "id" | "vector_updated_at" | "created_at">, profileId?: number) =>
    client.post(
      profileId ? `/users/me/companies/${profileId}/directions/` : "/users/me/directions/",
      data,
    ).then((r) => r.data as CompanyDirection),
  update: (id: number, data: Partial<CompanyDirection>, profileId?: number) =>
    client.patch(
      profileId ? `/users/me/companies/${profileId}/directions/${id}/` : `/users/me/directions/${id}/`,
      data,
    ).then((r) => r.data as CompanyDirection),
  remove: (id: number, profileId?: number) =>
    client.delete(
      profileId ? `/users/me/companies/${profileId}/directions/${id}/` : `/users/me/directions/${id}/`,
    ),
}

// Billing
export interface UserPlan {
  plan: "free" | "standard" | "premium"
  expires_at: string | null
  ai_summaries: { used: number; limit: number }
  rag_questions: { used: number; limit: number }
  companies: { used: number; limit: number }
  reset_at: string
}

export const billingApi = {
  getInfo: () =>
    client.get("/billing/me/").then((r) => r.data.data as UserPlan),
}

// Experiments
export const experimentsApi = {
  listForTender: (tenderId: number) =>
    client.get("/experiments/", { params: { tender_id: tenderId } })
      .then((r) => r.data.data as ExperimentSummary[]),

  getRuns: (experimentId: number, tenderId: number) =>
    client.get(`/experiments/${experimentId}/runs/`, { params: { tender_id: tenderId } })
      .then((r) => r.data.data as ExperimentRun[]),
}
