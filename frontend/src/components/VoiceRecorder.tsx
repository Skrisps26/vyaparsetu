import { Mic, Pause, Upload, Volume2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import WaveSurfer from 'wavesurfer.js'
import RecordPlugin from 'wavesurfer.js/dist/plugins/record.esm.js'
import { Button } from './ui/button'

interface Props {
  disabled?: boolean
  onRecorded: (audio: Blob) => void
  onRecordingStart?: () => void
  onDemo: () => void
  busy: boolean
  copy: Record<string, string>
}

export function VoiceRecorder({ disabled, onRecorded, onRecordingStart, onDemo, busy, copy }: Props) {
  const onRecordedRef = useRef(onRecorded)
  const waveform = useRef<HTMLDivElement>(null)
  const wave = useRef<WaveSurfer | null>(null)
  const recorder = useRef<RecordPlugin | null>(null)
  const starting = useRef(false)
  const stopRequested = useRef(false)
  const pointer = useRef<{ time: number; wasRecording: boolean } | null>(null)
  const [recording, setRecording] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [available, setAvailable] = useState(true)
  onRecordedRef.current = onRecorded

  useEffect(() => {
    if (!waveform.current) return
    let mounted = true
    const instance = WaveSurfer.create({ container: waveform.current, height: 68, waveColor: '#a5b4fc', progressColor: '#4f46e5', cursorWidth: 0, interact: false, normalize: true })
    const record = instance.registerPlugin(RecordPlugin.create({ scrollingWaveform: true, renderRecordedAudio: false }))
    record.on('record-progress', (time) => { if (mounted) setSeconds(Math.floor(time / 1000)) })
    record.on('record-end', (blob) => {
      record.stopMic()
      if (!mounted) return
      setRecording(false)
      setSeconds(0)
      onRecordedRef.current(blob)
    })
    wave.current = instance
    recorder.current = record
    return () => { mounted = false; stopRequested.current = true; record.stopRecording(); record.stopMic(); instance.destroy() }
  }, [])

  const start = async () => {
    if (disabled || busy || starting.current || recorder.current?.isRecording()) return
    starting.current = true
    stopRequested.current = false
    onRecordingStart?.()
    try {
      await recorder.current?.startRecording({ echoCancellation: true, noiseSuppression: true, channelCount: 1 })
      setRecording(true)
      if (stopRequested.current) recorder.current?.stopRecording()
    } catch { setAvailable(false) }
    finally { starting.current = false }
  }
  const stop = () => {
    stopRequested.current = true
    if (recorder.current?.isRecording()) recorder.current.stopRecording()
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.repeat || (event.target instanceof HTMLElement && event.target.closest('input, textarea, select, button, [role="dialog"]'))) return
      event.preventDefault()
      recorder.current?.isRecording() ? stop() : void start()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  useEffect(() => {
    const abort = () => stop()
    const visibility = () => { if (document.hidden) stop() }
    window.addEventListener('blur', abort)
    document.addEventListener('visibilitychange', visibility)
    const timer = recording ? window.setTimeout(stop, 25_000) : undefined
    return () => { window.clearTimeout(timer); window.removeEventListener('blur', abort); document.removeEventListener('visibilitychange', visibility) }
  }, [recording])

  return <section aria-labelledby="record-heading" className="surface-panel p-5 sm:p-6">
    <div className="flex items-start justify-between gap-3"><div><h2 id="record-heading" className="text-xl font-bold tracking-tight">{copy.record}</h2><p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{recording ? `${seconds}s / 25s` : copy.hold}</p></div><span className={`status-dot ${recording ? 'bg-rose-500' : 'bg-slate-400'}`} aria-label={recording ? 'Recording' : 'Idle'} /></div>
    <div ref={waveform} className="mt-5 h-[68px] rounded-xl bg-indigo-50 px-2 dark:bg-indigo-950/45" aria-label="Microphone waveform" />
    <div className="mt-5 grid grid-cols-[1fr_auto] gap-3">
      <button type="button" disabled={disabled || busy || !available}
        onPointerDown={(event) => { if (event.button !== 0) return; event.currentTarget.setPointerCapture(event.pointerId); pointer.current = { time: performance.now(), wasRecording: Boolean(recorder.current?.isRecording()) }; if (!pointer.current.wasRecording) void start() }}
        onPointerUp={() => { const press = pointer.current; pointer.current = null; if (press && (press.wasRecording || performance.now() - press.time > 250)) stop() }}
        onPointerCancel={() => { pointer.current = null; stop() }}
        onLostPointerCapture={() => { if (pointer.current) { pointer.current = null; stop() } }}
        onClick={(event) => { if (event.detail === 0) recorder.current?.isRecording() ? stop() : void start() }}
        className={`flex min-h-16 items-center justify-center gap-3 rounded-2xl text-base font-bold text-white outline-none transition focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 ${recording ? 'bg-rose-600' : 'bg-indigo-600 hover:bg-indigo-700'} disabled:opacity-45`} aria-pressed={recording}><Mic size={22} aria-hidden /><span>{recording ? <><Pause size={18} className="inline" /> {copy.release}</> : copy.record}</span></button>
      <label className="inline-flex min-h-16 cursor-pointer items-center justify-center rounded-2xl bg-slate-100 px-4 text-slate-700 transition hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-100"><Upload size={20} aria-hidden /><input className="sr-only" type="file" accept="audio/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) { onRecordingStart?.(); onRecorded(file) }; event.currentTarget.value = '' }} /><span className="sr-only">Upload audio file</span></label>
    </div>
    {!available && <p role="alert" className="mt-3 text-sm text-amber-700 dark:text-amber-300">{copy.micUnavailable}</p>}
    <div className="mt-4 flex items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-slate-800"><span className="text-xs font-medium text-slate-500 dark:text-slate-400">Space {copy.tap}</span><Button variant="secondary" onClick={() => { void wave.current?.load('/assets/demo-input.wav').catch(() => undefined); onDemo() }} disabled={busy || recording}><Volume2 size={17} />{copy.demo}</Button></div>
  </section>
}
