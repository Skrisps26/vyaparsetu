export type SourceMode = 'mock' | 'live' | 'cached' | 'manual'
export type PriceBasis = 'inclusive' | 'exclusive' | 'unknown'
export type Unit = 'kg' | 'g' | 'l' | 'ml' | 'piece' | 'pack'
export type PaymentMode = 'cash' | 'upi' | 'credit' | 'unknown'

export interface Config {
  use_mocks: boolean
  models: { stt: string; evon: string; tts: string }
  stages: Record<'stt' | 'evon' | 'tts', { configured: boolean; reason?: string | null }>
}

export interface Correction { item_index: number; field: 'quantity' | 'unit' | 'unit_price' | 'item'; old_value: string; new_value: string }
export interface DraftItem {
  catalog_id: string | null
  spoken_name: string
  search_query: string | null
  quantity: string
  unit: Unit
  unit_price: string | null
  gst_rate?: string | null
  price_basis?: PriceBasis
  price_offer_id?: string | null
  tax_candidate_id?: string | null
  resolved_product_id?: string | null
  manual_reason?: string | null
  conditions_confirmed?: boolean
}
export interface Extraction { items: DraftItem[]; customer_name: string | null; payment_mode: PaymentMode; corrections: Correction[] }
export interface InvoiceItem extends DraftItem {
  name?: string
  line_total?: string
  taxable?: string
  tax?: string
  cgst?: string
  sgst?: string
  issues?: string[]
  evidence?: Array<{ kind?: string; sources?: Source[] }>
}
export interface Invoice extends Omit<Extraction, 'items'> {
  items: InvoiceItem[]
  subtotal?: string
  gst?: string
  cgst?: string
  sgst?: string
  total?: string
  needs_review?: boolean
}
export interface RunEvent { run_id: string; seq: number; type: string; source: SourceMode; payload: Record<string, unknown> }
export interface Run {
  run_id: string
  source: SourceMode
  status: string
  transcript?: string | null
  detected_language_code?: string | null
  invoice?: Invoice | null
  reply_text?: string | null
  audio_url?: string | null
  events?: RunEvent[]
  latencies?: Record<string, number | string>
  error?: { message?: string } | string | null
}
export interface Ledger { accounts: Array<{ customer_name: string; balance: string; scope: string }>; invoices: Array<Record<string, unknown>> }

export interface Source { id: string; url: string; title: string; publisher?: string | null; retrieved_at?: string | null; kind?: string; excerpt?: string | null; status?: string }
export interface Product { id: string; name: string; brand?: string | null; barcode?: string | null; pack_size?: string | null; source_id?: string | null; match_status: 'barcode_match' | 'user_selected' | 'candidate' }
export interface PriceOffer { id: string; product_id: string; amount: string; currency: string; price_kind: 'selling' | 'mrp' | 'observed'; price_basis: PriceBasis; seller?: string | null; location?: string | null; observed_at?: string | null; valid_until?: string | null; source_id?: string | null }
export interface TaxCandidate { id: string; hsn: string; description: string; cgst: string | null; sgst: string | null; igst: string | null; conditions?: string[]; effective_from?: string | null; effective_to?: string | null; source_id?: string | null; status: 'snapshot' | 'unreviewed' | 'unknown' }
export interface LookupResult { lookup_id: string; products: Product[]; price_offers: PriceOffer[]; tax_candidates: TaxCandidate[]; sources: Source[]; status: 'ready' | 'partial' | 'not_found' | 'source_unavailable'; issues: string[] }
