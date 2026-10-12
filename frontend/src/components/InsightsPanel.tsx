import { Lightbulb } from 'lucide-react'
import type { AnalysisResponse } from '../api/types'

export function InsightsPanel({ data }: { data: AnalysisResponse }) {
  return (
    <section className="panel insights" aria-label="Trend interpretation">
      <h2>
        <Lightbulb size={18} aria-hidden /> Trend interpretation
      </h2>
      <ul>
        {data.insights.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  )
}
