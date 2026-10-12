import { Info } from 'lucide-react'

export function InfoTip({ text }: { text: string }) {
  return (
    <span className="info-tip" tabIndex={0} role="note" aria-label={text} data-tip={text}>
      <Info size={13} aria-hidden />
    </span>
  )
}
