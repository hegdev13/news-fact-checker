import type { CheckStatus, HealthStatus, ReportDetail, ReportListItem } from '../types'

// Defaults to same-origin `/api`, which Vite proxies to the FastAPI backend
// (see vite.config.ts). Override with VITE_API_BASE_URL for a deployed stack.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init)
  if (!res.ok) {
    let message = `API error (HTTP ${res.status})`
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') message = body.detail
    } catch {
      // keep the generic message
    }
    throw new Error(message)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<HealthStatus>('/health'),

  /** All completed reports in the shared store, newest first. */
  listReports: () => request<ReportListItem[]>('/reports'),

  /** Full artifacts + audit trail for one claim. */
  getReport: (claimId: string) => request<ReportDetail>(`/reports/${claimId}`),

  /** Kick off a background fact-check of `claim`; returns the job/claim id. */
  startCheck: (claim: string) =>
    request<{ claim_id: string; status: string }>('/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ claim }),
    }),

  /** Poll a running check; `detail` is present once status === "done". */
  pollCheck: (claimId: string) => request<CheckStatus>(`/check/${claimId}`),

  /** Run the three bundled sample claims through the pipeline. */
  startDemo: () => request<{ claim_ids: string[]; count: number }>('/check/demo', { method: 'POST' }),
}