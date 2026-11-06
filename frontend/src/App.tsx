import { Languages, Moon, Play, RotateCcw, Sun, WifiOff } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTheme } from 'next-themes'
import { Toaster, toast } from 'sonner'
import { api, connectRunEvents } from './lib/api'
import type { Config, Extraction, Invoice, Ledger, Run, RunEvent, SourceMode } from './lib/types'
import { Badge } from './components/ui/badge'
import { Button } from './components/ui/button'
import { InvoicePanel } from './components/InvoicePanel'
import { ProductLookup } from './components/ProductLookup'
import type { LookupSelection } from './components/ProductLookup'
import { ReceiptPdf } from './components/ReceiptPdf'
import { VoiceRecorder } from './components/VoiceRecorder'

const cachedInvoice: Invoice = { items: [
  { catalog_id: 'demo-rice', spoken_name: 'ഡെമോ അരി', name: 'ഡെമോ അരി', search_query: null, quantity: '3', unit: 'kg', unit_price: '40.00', gst_rate: '5', price_basis: 'exclusive', line_total: '126.00', taxable: '120.00', tax: '6.00', cgst: '3.00', sgst: '3.00', issues: [] },
  { catalog_id: 'demo-soap', spoken_name: 'ഡെമോ സോപ്പ്', name: 'ഡെമോ സോപ്പ്', search_query: null, quantity: '1', unit: 'piece', unit_price: '20.00', gst_rate: '18', price_basis: 'exclusive', line_total: '23.60', taxable: '20.00', tax: '3.60', cgst: '1.80', sgst: '1.80', issues: [] },
], customer_name: 'Demo Kili', payment_mode: 'credit', corrections: [{ item_index: 0, field: 'quantity', old_value: '2', new_value: '3' }], subtotal: '140.00', gst: '9.60', cgst: '4.80', sgst: '4.80', total: '149.60', needs_review: false }
const offlineReply = 'ബിൽ തുക നൂറ്റി നാൽപ്പത്തൊൻപത് രൂപ അറുപത് പൈസ. ഡെമോ അക്കൗണ്ടിൽ ചേർത്തു. ആകെ ബാക്കി ഇരുനൂറ്റി നാൽപ്പത്തൊൻപത് രൂപ അറുപത് പൈസ.'
const fallbackConfig: Config = { use_mocks: true, models: { stt: 'prisma-v3.0', evon: 'gnani-evon-v3.3', tts: 'timbre-v3.0' }, stages: { stt: { configured: false, reason: 'Backend unavailable' }, evon: { configured: false, reason: 'Backend unavailable' }, tts: { configured: false, reason: 'Backend unavailable' } } }
const english = { record: 'Record', hold: 'Hold to record · tap or Space to start/stop', release: 'Release to stop', micUnavailable: 'Microphone access is unavailable. Upload a file or play the cached demo.', tap: 'toggles recording', demo: 'Replay demo', receipt: 'Receipt', confirm: 'Confirm & save', typeFind: 'Type / find items' }
const malayalam = { record: 'റെക്കോർഡ് ചെയ്യുക', hold: 'അമർത്തിപ്പിടിക്കുക · ടാപ്പ് അല്ലെങ്കിൽ Space ഉപയോഗിക്കുക', release: 'നിർത്താൻ വിടുക', micUnavailable: 'മൈക്രോഫോൺ ലഭ്യമല്ല. ഫയൽ അപ്ലോഡ് ചെയ്യുക അല്ലെങ്കിൽ ഡെമോ പ്ലേ ചെയ്യുക.', tap: 'റെക്കോർഡിംഗ് മാറും', demo: 'ഡെമോ വീണ്ടും പ്ലേ', receipt: 'രസീത്', confirm: 'സ്ഥിരീകരിച്ച് സേവ് ചെയ്യുക', typeFind: 'ടൈപ്പ് / ഇനം കണ്ടെത്തുക' }

function toReviewedItem(item: Invoice['items'][number]) {
  return {
    catalog_id: item.catalog_id,
    spoken_name: item.spoken_name,
    search_query: item.search_query,
    quantity: item.quantity,
    unit: item.unit,
    unit_price: item.unit_price,
    gst_rate: item.gst_rate ?? null,
    price_basis: item.price_basis ?? 'unknown',
    price_offer_id: item.price_offer_id ?? null,
    tax_candidate_id: item.tax_candidate_id ?? null,
    resolved_product_id: item.resolved_product_id ?? null,
    manual_reason: item.manual_reason ?? null,
    conditions_confirmed: item.conditions_confirmed ?? false,
  }
}


export default function App() {
  const { theme, setTheme } = useTheme()
  const [config, setConfig] = useState<Config>(fallbackConfig)
  const [run, setRun] = useState<Run | null>(null)
  const [invoice, setInvoice] = useState<Invoice | null>(null)
  const [ledger, setLedger] = useState<Ledger | null>(null)
  const [language, setLanguage] = useState<'ml' | 'en'>('ml')
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [lookupIndex, setLookupIndex] = useState<number | null>(null)
  const [lookupOpen, setLookupOpen] = useState(false)
  const [selectedLookup, setSelectedLookup] = useState<LookupSelection | null>(null)
  const [offline, setOffline] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const lastReply = useRef<string | null>(null)
  const audio = useRef<HTMLAudioElement | null>(null)
  const websocket = useRef<WebSocket | null>(null)
  const copy = language === 'ml' ? malayalam : english
  const source: SourceMode = run?.source ?? (offline ? 'cached' : config.use_mocks ? 'mock' : 'manual')
  const currentStatus = run?.status ?? (invoice ? (editing ? 'review' : 'ready') : 'idle')
  const activeAccount = run?.source === 'cached' ? undefined : ledger?.accounts.find((account) => account.customer_name === invoice?.customer_name && account.scope === (run?.source === 'mock' ? `demo:${run.run_id}` : 'live'))
  const accountName = invoice?.customer_name ?? 'No credit account'
  const accountBalance = run?.source === 'cached' ? '249.60' : activeAccount?.balance ?? (run?.source === 'mock' ? '100.00' : '0')
  const saved = ['saved', 'complete', 'completed'].includes(run?.status ?? '')

  useEffect(() => { api.config().then(setConfig).then(() => setOffline(false)).catch(() => setOffline(true)); api.ledger().then(setLedger).catch(() => undefined) }, [])
  useEffect(() => () => { websocket.current?.close(); audio.current?.pause() }, [])

  const loadRun = useCallback(async (runId: string) => {
    try { const snapshot = await api.run(runId); setRun(snapshot); setInvoice(snapshot.invoice ?? null); setEditing(Boolean(snapshot.invoice?.needs_review)); setBusy(['queued', 'transcribing', 'understanding', 'synthesizing'].includes(snapshot.status)) } catch (error) { setBusy(false); toast.error(error instanceof Error ? error.message : 'Could not load this run.') }
  }, [])
  const watch = useCallback((runId: string) => {
    websocket.current?.close()
    websocket.current = connectRunEvents(runId, 0, (event: RunEvent) => { void loadRun(event.run_id) }, () => toast.message('Live event connection ended; latest state remains visible.'))
    void loadRun(runId)
  }, [loadRun])
  const beginRun = useCallback(async (request: () => Promise<{ run_id: string }>) => {
    setBusy(true); setOffline(false); setRun(null); setInvoice(null); setEditing(false)
    try { const { run_id } = await request(); watch(run_id) } catch (error) { setBusy(false); toast.error(error instanceof Error ? error.message : 'Could not start processing.') }
  }, [watch])
  const replayDemo = useCallback(async () => {
    setBusy(true)
    try { const { run_id } = await api.runScenario(); setOffline(false); watch(run_id); play('/assets/demo-input.wav') } catch {
      setOffline(true); setBusy(false); setEditing(false); setRun({ run_id: 'cached-demo', source: 'cached', status: 'completed', transcript: 'ഡെമോ അരി two kilo, അല്ല three kilo, കിലോയ്ക്ക് forty rupees; ഡെമോ സോപ്പ് one piece twenty rupees; ഡെമോ കിളിയുടെ അക്കൗണ്ടിൽ കടമായി ഇടൂ.', detected_language_code: 'ml-IN', invoice: cachedInvoice, reply_text: offlineReply, audio_url: '/assets/demo-reply.wav', latencies: { transcription: 'replay', extraction: 'replay', reply: 'replay' } }); setInvoice(cachedInvoice); playCachedDemo()
    }
  }, [watch])
  const play = (url?: string | null) => {
    if (!url) return
    audio.current?.pause()
    const player = new Audio(url)
    audio.current = player
    player.onplaying = () => setSpeaking(true)
    player.onended = player.onpause = () => setSpeaking(false)
    player.onerror = () => { setSpeaking(false); toast.error('Audio could not play. The saved bill is unchanged.') }
    player.play().catch(() => { setSpeaking(false); toast.message('Autoplay is blocked. Use the Play confirmation button.') })
  }
  useEffect(() => {
    if (run?.source !== 'cached' && run?.audio_url && run.audio_url !== lastReply.current) {
      lastReply.current = run.audio_url
      play(run.audio_url)
    }
  }, [run?.audio_url])
  const playCachedDemo = () => {
    audio.current?.pause()
    const input = new Audio('/assets/demo-input.wav')
    audio.current = input
    input.onended = () => play('/assets/demo-reply.wav')
    input.play().catch(() => play('/assets/demo-reply.wav'))
  }
  const createDraft = async () => {
    const initial: Extraction = { items: [{ catalog_id: null, spoken_name: 'Draft item', search_query: null, quantity: '1', unit: 'piece', unit_price: null, gst_rate: null, price_basis: 'unknown', manual_reason: null, conditions_confirmed: false }], customer_name: null, payment_mode: 'unknown', corrections: [] }
    try { const { run_id } = await api.createDraft(initial); setOffline(false); watch(run_id) } catch { setRun(null); setInvoice({ ...initial, needs_review: true }); setEditing(true); setOffline(true); toast.error('Backend unavailable. You can prepare the draft, but it cannot be saved until the backend reconnects.') }
  }
  const confirm = async () => { if (!run || !invoice || run.source === 'cached') { if (run?.source === 'cached') play('/assets/demo-reply.wav'); return } try { setBusy(true); const updated = await api.confirm(run.run_id, { items: invoice.items.map(toReviewedItem), customer_name: invoice.customer_name, payment_mode: invoice.payment_mode }); setRun(updated); setInvoice(updated.invoice ?? invoice); setEditing(false); setBusy(false); void api.ledger().then(setLedger) } catch (error) { setBusy(false); toast.error(error instanceof Error ? error.message : 'Confirmation failed.') } }
  const selectEvidence = (selection: LookupSelection) => { if (lookupIndex == null || !invoice) return; const items = invoice.items.map((item, index) => index !== lookupIndex ? item : { ...item, spoken_name: selection.product?.name ?? item.spoken_name, resolved_product_id: selection.product?.id ?? item.resolved_product_id, unit_price: selection.offer?.amount ?? item.unit_price, price_offer_id: selection.offer?.id ?? item.price_offer_id, price_basis: selection.offer?.price_basis ?? item.price_basis, tax_candidate_id: selection.tax?.id ?? item.tax_candidate_id, gst_rate: selection.tax?.cgst && selection.tax?.sgst ? String(Number(selection.tax.cgst) + Number(selection.tax.sgst)) : item.gst_rate, conditions_confirmed: selection.conditionsConfirmed }); setInvoice({ ...invoice, items, needs_review: true }); setSelectedLookup(selection); setEditing(true) }
  const latencies = useMemo(() => Object.entries(run?.latencies ?? {}).slice(0, 4), [run])
  const rememberSelection = async () => {
    if (!selectedLookup) return
    try {
      const chosenItem = invoice?.items.find((item) => item.resolved_product_id === selectedLookup.product?.id)
      await api.rememberLookup(selectedLookup.lookupId, selectedLookup.product?.id ?? null, selectedLookup.offer?.id ?? null, selectedLookup.tax?.id ?? null, chosenItem?.price_basis ?? 'unknown', chosenItem?.conditions_confirmed ?? selectedLookup.conditionsConfirmed)
      toast.success('Saved for this shop. Re-review it when source dates change.')
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not remember this selection.') }
  }

  return <main className="min-h-dvh bg-slate-50 text-slate-900 selection:bg-indigo-200 dark:bg-slate-950 dark:text-slate-50"><Toaster richColors position="top-center" /><header className="app-header"><div className="app-frame flex min-h-16 items-center justify-between gap-3"><div><h1 className="text-lg font-black tracking-[-.03em] sm:text-xl">വ്യാപാരസേതു <span className="font-semibold text-slate-500 dark:text-slate-400">VyaparSetu</span></h1><p className="text-xs font-medium text-slate-500 dark:text-slate-400">Malayalam voice ledger</p></div><div className="flex items-center gap-1"><Button variant="quiet" aria-label="Switch language" onClick={() => setLanguage(language === 'ml' ? 'en' : 'ml')}><Languages size={18} /><span className="hidden sm:inline">{language === 'ml' ? 'EN' : 'മ'}</span></Button><Button variant="quiet" aria-label="Switch theme" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}</Button></div></div></header>
    <div className="app-frame py-5 sm:py-7"><div className="mb-5 flex flex-wrap items-center gap-2"><Badge className={source === 'live' ? 'source-live' : source === 'cached' ? 'source-cached' : source === 'manual' ? 'source-manual' : 'source-mock'}><span className="status-dot" />{source === 'cached' ? 'Cached demo replay' : source === 'manual' ? 'Manual draft' : source === 'mock' ? 'Mock fixture' : 'Live pipeline'}</Badge><Badge>{config.models.stt || 'prisma-v3.0'}</Badge><Badge title={config.models.evon || 'Not configured'}>gnani-evon-v3.3</Badge><Badge>{config.models.tts || 'timbre-v3.0'}</Badge>{offline && <Badge className="border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"><WifiOff size={13} />Backend disconnected</Badge>}</div>
      <div className="operate-grid"><div className="space-y-5"><VoiceRecorder busy={busy} disabled={!config.stages.stt.configured && !config.use_mocks} onRecordingStart={() => audio.current?.pause()} onRecorded={(audioBlob) => void beginRun(() => api.uploadAudio(audioBlob))} onDemo={() => void replayDemo()} copy={copy} />
        <section className="surface-panel p-5 sm:p-6"><div className="flex items-start justify-between gap-3"><div><h2 className="text-xl font-bold tracking-tight">Transcript</h2><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{run?.detected_language_code ? `Detected: ${run.detected_language_code}` : 'Language: Unknown'}</p></div>{busy && <span className="stage-chip">Processing</span>}</div><p className="mt-5 min-h-24 whitespace-pre-wrap text-base leading-8 text-slate-800 dark:text-slate-100">{run?.transcript || 'Release the microphone to receive the full transcription. REST transcription is returned after recording, not word by word.'}</p>{run?.error && <p role="alert" className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-900 dark:bg-rose-950/40 dark:text-rose-100">{typeof run.error === 'string' ? run.error : run.error.message}</p>}<div className="mt-5 flex flex-wrap gap-2"><Button variant="secondary" onClick={() => void createDraft()}>Type / find items</Button>{run?.source === 'cached' && <Button variant="quiet" onClick={() => void replayDemo()}><RotateCcw size={17} />Restart demo</Button>}</div></section>
        <section className="surface-panel p-5 sm:p-6"><div className="flex items-center justify-between gap-2"><h2 className="text-xl font-bold tracking-tight">{language === 'ml' ? 'മറുപടി' : 'Reply'}</h2><span role="status" className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">{speaking ? (language === 'ml' ? 'സംസാരിക്കുന്നു…' : 'Speaking…') : ''}</span></div><p className="mt-3 leading-7 text-slate-700 dark:text-slate-200">{run?.reply_text || 'A Malayalam confirmation is available after a saved bill.'}</p><div className="mt-4 flex flex-wrap items-center gap-3"><Button variant="secondary" disabled={!run?.audio_url} onClick={() => play(run?.audio_url)}><Play size={17} />Play confirmation</Button>{(run?.source === 'cached' || run?.source === 'mock') && <span className="text-xs text-slate-500">Mock voice — eSpeak NG</span>}<ReceiptPdf invoice={invoice} /></div></section></div>
        <div className="space-y-5"><InvoicePanel invoice={invoice} editing={editing} onChange={setInvoice} onOpenLookup={(index) => { setLookupIndex(index); setLookupOpen(true) }} onCreate={() => void createDraft()} onConfirm={() => void confirm()} confirmDisabled={busy || saved || !invoice || (run?.source !== 'cached' && !run)} copy={{ ...copy, confirm: saved ? (language === 'ml' ? 'സേവ് ചെയ്തു' : 'Saved to ledger') : copy.confirm }} />
        <section className="surface-panel p-5 sm:p-6"><h2 className="text-lg font-bold">{language === 'ml' ? 'കടപ്പുസ്തകം' : 'Credit ledger'}</h2><div className="mt-3 flex items-end justify-between gap-3"><div><p className="text-sm text-slate-600 dark:text-slate-300">{accountName}</p><p className="mt-1 text-xs text-slate-500">{run?.source === 'cached' ? 'Cached replay · isolated' : run?.source === 'mock' ? 'Synthetic demo account' : 'Local account balance'}</p></div><strong className="text-2xl tabular-nums">₹{Number(accountBalance).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></div>{selectedLookup && saved && run?.source !== 'cached' && <Button variant="secondary" className="mt-4 w-full" onClick={() => void rememberSelection()}>Remember for my shop</Button>}</section></div></div>
      <footer className="mt-5 border-t border-slate-200 py-4 dark:border-slate-800"><div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500"><span>Demo customers and transactions are synthetic · Product information from public sources</span><span className="font-medium">{currentStatus}</span></div><div className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2 text-xs text-slate-600 dark:text-slate-300 sm:flex sm:flex-wrap">{latencies.length ? latencies.map(([stage, value]) => <span key={stage}><b>{stage}</b> {typeof value === 'number' ? `${value} ms` : value}</span>) : <span>Stage timings appear from real provider responses; cached replay is labeled replay.</span>}</div></footer>
    </div><ProductLookup open={lookupOpen} onOpenChange={setLookupOpen} initialQuery={lookupIndex == null ? '' : invoice?.items[lookupIndex]?.search_query ?? invoice?.items[lookupIndex]?.spoken_name ?? ''} itemUnit={lookupIndex == null ? undefined : invoice?.items[lookupIndex]?.unit} onSelect={selectEvidence} />
    {invoice && <div className="mobile-bill-bar"><span>{language === 'ml' ? 'ആകെ' : 'Total'} <strong>₹{invoice.total == null ? '—' : Number(invoice.total).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</strong></span><Button variant="secondary" onClick={() => document.getElementById('receipt-heading')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{language === 'ml' ? 'ബിൽ കാണുക' : 'View bill'}</Button></div>}
  </main>
}
