import { useRef, useState } from 'react'
import { Download, LoaderCircle } from 'lucide-react'
import type { Invoice } from '../lib/types'
import { Button } from './ui/button'

const amount = (value?: string | null) => value == null ? '—' : `₹${Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/** Browser text shaping preserves Malayalam conjuncts; PDF export is intentionally raster. */
export function ReceiptPdf({ invoice }: { invoice: Invoice | null }) {
  const receipt = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!invoice) return null
  const pages = Array.from({ length: Math.ceil(invoice.items.length / 10) }, (_, index) => invoice.items.slice(index * 10, index * 10 + 10))

  const download = async () => {
    if (!receipt.current || exporting) return
    setExporting(true)
    setError(null)
    try {
      await document.fonts.ready
      const [{ default: html2canvas }, { jsPDF }] = await Promise.all([import('html2canvas'), import('jspdf')])
      const pdf = new jsPDF({ orientation: 'portrait', unit: 'pt', format: 'a4' })
      const sheets = Array.from(receipt.current.children) as HTMLElement[]
      for (let index = 0; index < sheets.length; index++) {
        const canvas = await html2canvas(sheets[index], { scale: 2, backgroundColor: '#ffffff', logging: false, useCORS: false })
        if (index) pdf.addPage()
        const scale = Math.min(539 / canvas.width, 786 / canvas.height)
        pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 28, 28, canvas.width * scale, canvas.height * scale)
      }
      pdf.save('vyaparsetu-demo-receipt.pdf')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'PDF export failed. Please try again.')
    } finally {
      setExporting(false)
    }
  }

  return <div>
    <Button variant="secondary" onClick={() => void download()} disabled={exporting || invoice.total == null}>
      {exporting ? <LoaderCircle size={17} className="animate-spin" /> : <Download size={17} />}
      {exporting ? 'Preparing PDF…' : 'PDF receipt'}
    </Button>
    {error && <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-300">{error}</p>}
    <div ref={receipt} aria-hidden="true" style={{ position: 'fixed', left: '-10000px', top: 0, width: 720, pointerEvents: 'none', color: '#0f172a', backgroundColor: '#ffffff' }}>
      {pages.map((items, pageIndex) => <div key={pageIndex} style={{ width: 720, padding: 28, boxSizing: 'border-box', fontFamily: 'NotoReceipt, sans-serif', fontSize: 14, lineHeight: 1.7, color: '#0f172a', backgroundColor: '#ffffff' }}>
        <div style={{ fontSize: 25, fontWeight: 700 }}>വ്യാപാരസേതു · VyaparSetu</div>
        <p style={{ fontSize: 12, color: '#475569' }}>Demo transaction · synthetic customer · not for tax filing</p>
        <p>{invoice.customer_name || 'Cash customer'} · {invoice.payment_mode.toUpperCase()} · Page {pageIndex + 1}/{pages.length}</p>
        <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed', fontSize: 13 }}>
          <thead><tr><th style={{ textAlign: 'left', width: '42%' }}>Item / ഇനം</th><th>Quantity</th><th>GST</th><th style={{ textAlign: 'right' }}>Total</th></tr></thead>
          <tbody>{items.map((item, index) => <tr key={index} style={{ borderBottom: '1px solid #cbd5e1' }}><td style={{ padding: '12px 4px', overflowWrap: 'anywhere' }}>{item.name || item.spoken_name}<div style={{ color: '#475569', fontSize: 11 }}>{amount(item.unit_price)} · {item.price_basis}</div>{item.manual_reason && <div style={{ fontSize: 10 }}>User provided: {item.manual_reason}</div>}</td><td style={{ textAlign: 'center' }}>{item.quantity} {item.unit}</td><td style={{ textAlign: 'center' }}>{item.gst_rate ?? 'Unknown'}%</td><td style={{ textAlign: 'right' }}>{amount(item.line_total)}</td></tr>)}</tbody>
        </table>
        {pageIndex === pages.length - 1 && <div style={{ marginTop: 18 }}><div>Subtotal: {amount(invoice.subtotal)}</div><div>CGST: {amount(invoice.cgst)} · SGST: {amount(invoice.sgst)}</div><div style={{ fontSize: 22, fontWeight: 700 }}>Total / ആകെ: {amount(invoice.total)}</div>{invoice.corrections.map((correction, index) => <p key={index}>Correction: {correction.old_value} → {correction.new_value}</p>)}</div>}
        {items.map((item, index) => (item.evidence ?? []).flatMap((entry) => entry.sources ?? []).map((entry, sourceIndex) => <p key={`${index}-${sourceIndex}`} style={{ fontSize: 10, overflowWrap: 'anywhere', color: '#475569' }}>Source: {entry.title} · {entry.url}</p>))}
        <p style={{ fontSize: 10, color: '#475569' }}>Product references may be public. Demo customers and transactions are synthetic. This PDF preserves browser-shaped Malayalam as images; its text is not searchable.</p>
      </div>)}
    </div>
  </div>
}
