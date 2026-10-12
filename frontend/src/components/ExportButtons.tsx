import { useState } from 'react'
import { CheckCircle2, FileDown, FileText, Loader2, XCircle } from 'lucide-react'
import { downloadExport, type QueryParams } from '../api/client'

type Status = { kind: 'idle' } | { kind: 'busy'; format: 'csv' | 'pdf' } | { kind: 'ok' | 'error'; message: string }

export function ExportButtons({ params, disabled }: { params: QueryParams | null; disabled?: boolean }) {
  const [status, setStatus] = useState<Status>({ kind: 'idle' })
  const busy = status.kind === 'busy'

  const run = async (format: 'csv' | 'pdf') => {
    if (!params) return
    setStatus({ kind: 'busy', format })
    try {
      const filename = await downloadExport(format, params)
      setStatus({ kind: 'ok', message: `Downloaded ${filename}` })
    } catch (err) {
      setStatus({ kind: 'error', message: (err as Error).message || 'Export failed.' })
    }
  }

  const off = disabled || !params || busy
  return (
    <div className="exports">
      <button type="button" className="secondary" onClick={() => run('csv')} disabled={off}>
        {busy && status.format === 'csv' ? <Loader2 size={16} className="spin" aria-hidden /> : <FileDown size={16} aria-hidden />}
        Export CSV
      </button>
      <button type="button" className="secondary" onClick={() => run('pdf')} disabled={off}>
        {busy && status.format === 'pdf' ? <Loader2 size={16} className="spin" aria-hidden /> : <FileText size={16} aria-hidden />}
        Export PDF
      </button>
      <span className="export-status" role="status" aria-live="polite">
        {status.kind === 'busy' && `Preparing ${status.format.toUpperCase()}…`}
        {status.kind === 'ok' && (
          <>
            <CheckCircle2 size={14} aria-hidden /> {status.message}
          </>
        )}
        {status.kind === 'error' && (
          <span className="error-text">
            <XCircle size={14} aria-hidden /> {status.message}
          </span>
        )}
      </span>
    </div>
  )
}
