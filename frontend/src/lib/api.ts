import type { Config, Extraction, Ledger, LookupResult, Run, RunEvent } from './types'

const jsonHeaders = { 'Content-Type': 'application/json' }

async function request<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try { detail = (await response.json()).detail ?? detail } catch { /* preserve status */ }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  config: () => request<Config>('/api/config'),
  runScenario: () => request<{ run_id: string }>('/api/runs', { method: 'POST', headers: jsonHeaders, body: JSON.stringify({ scenario_id: 'correction-credit' }) }),
  uploadAudio: (audio: Blob) => {
    const body = new FormData()
    body.set('audio_file', audio, 'clip.webm')
    return request<{ run_id: string }>('/api/runs', { method: 'POST', body })
  },
  run: (runId: string) => request<Run>(`/api/runs/${encodeURIComponent(runId)}`),
  confirm: (runId: string, body?: Partial<Extraction>) => request<Run>(`/api/runs/${encodeURIComponent(runId)}/confirm`, { method: 'POST', headers: jsonHeaders, body: JSON.stringify(body ?? {}) }),
  ledger: () => request<Ledger>('/api/ledger'),
  createDraft: (extraction: Extraction) => request<{ run_id: string }>('/api/drafts', { method: 'POST', headers: jsonHeaders, body: JSON.stringify(extraction) }),
  lookup: (query: string) => request<LookupResult>('/api/lookup', { method: 'POST', headers: jsonHeaders, body: JSON.stringify({ query, barcode: null, pack_size: null, location: null, as_of_date: new Date().toISOString().slice(0, 10) }) }),
  rememberLookup: (lookupId: string, productId: string | null, priceOfferId: string | null, taxCandidateId: string | null, priceBasis: string, conditionsConfirmed: boolean) => request<void>(`/api/lookup/${encodeURIComponent(lookupId)}/remember`, { method: 'POST', headers: jsonHeaders, body: JSON.stringify({ product_id: productId, price_offer_id: priceOfferId, tax_candidate_id: taxCandidateId, price_basis: priceBasis, conditions_confirmed: conditionsConfirmed }) }),
}

export function connectRunEvents(runId: string, after: number, onEvent: (event: RunEvent) => void, onFailure: () => void) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const socket = new WebSocket(`${protocol}//${location.host}/api/runs/${encodeURIComponent(runId)}/events?after=${after}`)
  socket.onmessage = ({ data }) => {
    try { onEvent(JSON.parse(data) as RunEvent) } catch { /* malformed frames never mutate UI */ }
  }
  socket.onerror = onFailure
  return socket
}
