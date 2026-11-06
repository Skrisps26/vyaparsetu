import { ExternalLink, LoaderCircle, Search, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import type { LookupResult, PriceBasis, Product, PriceOffer, TaxCandidate } from '../lib/types'
import { api } from '../lib/api'
import { Button } from './ui/button'
import { Input } from './ui/input'
import { Sheet, SheetContent, SheetDescription, SheetTitle } from './ui/sheet'
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs'

export interface LookupSelection {
  lookupId: string
  product?: Product
  offer?: PriceOffer
  tax?: TaxCandidate
  conditionsConfirmed: boolean
}

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialQuery?: string
  itemUnit?: string
  onSelect: (selection: LookupSelection) => void
}

export function ProductLookup({ open, onOpenChange, initialQuery = '', itemUnit, onSelect }: Props) {
  const [query, setQuery] = useState(initialQuery)
  const [result, setResult] = useState<LookupResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Omit<LookupSelection, 'lookupId'>>({ conditionsConfirmed: false })
  const [conditionsConfirmed, setConditionsConfirmed] = useState(false)
  useEffect(() => { if (open) setQuery(initialQuery) }, [initialQuery, open])
  const sources = useMemo(() => new Map(result?.sources.map((source) => [source.id, source])), [result])
  const sourceName = (sourceId?: string | null) => sources.get(sourceId ?? '')?.publisher || sources.get(sourceId ?? '')?.title || 'Source link'
  const offerNeedsProduct = Boolean(selected.offer && !selected.product)
  const packNeedsConversion = Boolean(selected.offer && selected.product?.pack_size && itemUnit && itemUnit !== 'pack' && itemUnit !== 'piece')

  const search = async (event: FormEvent) => {
    event.preventDefault()
    if (query.trim().length < 2) { setError('Enter at least two characters to search.'); return }
    setLoading(true)
    setError(null)
    try {
      setResult(await api.lookup(query.trim()))
      setSelected({ conditionsConfirmed: false })
      setConditionsConfirmed(false)
    } catch (cause) {
      setResult(null)
      setError(cause instanceof Error ? cause.message : 'Source lookup is unavailable.')
    } finally { setLoading(false) }
  }
  const choose = () => {
    if (!result || (!selected.product && !selected.offer && !selected.tax) || offerNeedsProduct || packNeedsConversion || ((selected.tax?.conditions?.length ?? 0) > 0 && !conditionsConfirmed)) return
    onSelect({ ...selected, lookupId: result.lookup_id, conditionsConfirmed })
    onOpenChange(false)
  }
  const money = (amount: string) => `₹${Number(amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
  const basis = (value: PriceBasis) => value === 'inclusive' ? 'GST included' : value === 'exclusive' ? 'GST extra' : 'Tax basis needs review'
  const selectionDisabled = (!selected.product && !selected.offer && !selected.tax) || offerNeedsProduct || packNeedsConversion || (selected.tax?.conditions?.length ?? 0) > 0 && !conditionsConfirmed

  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent><div className="pr-9"><SheetTitle className="text-2xl font-bold tracking-tight">Find item / വിലയും GSTയും</SheetTitle><SheetDescription className="mt-1 text-sm text-slate-600 dark:text-slate-300">Choose product, price, and tax evidence separately. Nothing is selected automatically.</SheetDescription></div>
    <form onSubmit={search} className="mt-6 flex gap-2"><Input aria-label="Product query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Amul butter 100 g" /><Button disabled={loading}>{loading ? <LoaderCircle className="animate-spin" /> : <Search size={18} />}Search</Button></form>
    {error && <p role="alert" className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-100">{error} You can enter a shop price and manual tax reason in the review form.</p>}
    {result && <><p className="mt-4 text-xs font-semibold text-slate-500">Status: {result.status.replace('_', ' ')} · {result.issues.join(' · ')}</p><Tabs defaultValue="products" className="mt-4"><TabsList><TabsTrigger value="products">Products</TabsTrigger><TabsTrigger value="prices">Prices</TabsTrigger><TabsTrigger value="gst">GST evidence</TabsTrigger></TabsList>
      <TabsContent value="products" className="lookup-list">{result.products.length ? result.products.map((product) => <button type="button" key={product.id} onClick={() => setSelected((previous) => ({ ...previous, product }))} className={`lookup-row ${selected.product?.id === product.id ? 'selected' : ''}`}><strong>{product.name}</strong><span>{[product.brand, product.pack_size, product.match_status.replace('_', ' ')].filter(Boolean).join(' · ')}</span></button>) : <Empty text="No product identity was returned. Keep the item editable and enter it manually." />}</TabsContent>
      <TabsContent value="prices" className="lookup-list">{result.price_offers.length ? result.price_offers.map((offer) => <EvidenceChoice key={offer.id} selected={selected.offer?.id === offer.id} onChoose={() => setSelected((previous) => ({ ...previous, offer }))} source={sources.get(offer.source_id ?? '')} label={sourceName(offer.source_id)}><strong>{money(offer.amount)} <small>{offer.currency}</small></strong><span>{offer.price_kind.toUpperCase()} · {basis(offer.price_basis)} · {[offer.seller, offer.location, offer.observed_at].filter(Boolean).join(' · ')}</span></EvidenceChoice>) : <Empty text="No structured price offer. A discovery card is not a shop price." />}</TabsContent>
      <TabsContent value="gst" className="lookup-list">{result.tax_candidates.length ? result.tax_candidates.map((tax) => <EvidenceChoice key={tax.id} selected={selected.tax?.id === tax.id} onChoose={() => setSelected((previous) => ({ ...previous, tax }))} source={sources.get(tax.source_id ?? '')} label={sourceName(tax.source_id)}><strong><ShieldCheck size={16} /> HSN {tax.hsn} · {tax.status}</strong><span>{tax.description}</span><span>CGST {tax.cgst ?? '—'}% · SGST {tax.sgst ?? '—'}% {tax.conditions?.length ? `· ${tax.conditions.join(' · ')}` : ''}</span></EvidenceChoice>) : <Empty text="No reviewed tax rule was found. Do not assume a zero rate; use a documented manual override if appropriate." />}</TabsContent>
    </Tabs>{(selected.tax?.conditions?.length ?? 0) > 0 && <label className="mt-4 flex items-start gap-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/40 dark:text-amber-100"><input type="checkbox" checked={conditionsConfirmed} onChange={(event) => setConditionsConfirmed(event.target.checked)} className="mt-1 h-4 w-4 accent-indigo-600" />I reviewed and confirm: {selected.tax?.conditions?.join(' · ')}</label>}{offerNeedsProduct && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/40 dark:text-amber-100">Select the matching product identity before using its observed offer.</p>}{packNeedsConversion && <p className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950/40 dark:text-amber-100">This is a {selected.product?.pack_size} pack price, while this row uses {itemUnit}. No per-unit conversion is applied. Change the line to pack or enter an explicit manual unit price.</p>}<Button className="mt-6 w-full" disabled={selectionDisabled} onClick={choose}>Use selected evidence</Button></>}
  </SheetContent></Sheet>
}
function EvidenceChoice({ selected, onChoose, source, label, children }: { selected: boolean; onChoose: () => void; source?: LookupResult['sources'][number]; label: string; children: ReactNode }) { return <div className={`lookup-row ${selected ? 'selected' : ''}`}><button type="button" onClick={onChoose} className="w-full text-left">{children}</button><SourceLink source={source} label={label} /></div> }
function SourceLink({ source, label }: { source?: LookupResult['sources'][number]; label: string }) { return source?.url ? <a href={source.url} target="_blank" rel="noreferrer noopener" className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-indigo-700 underline underline-offset-2 dark:text-indigo-300"><ExternalLink size={13} />{label}</a> : null }
function Empty({ text }: { text: string }) { return <p className="py-8 text-center text-sm text-slate-500 dark:text-slate-400">{text}</p> }
