import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { Loader2, Search } from 'lucide-react'
import { ApiError, searchPlaces } from '../api/client'
import type { Place } from '../api/types'
import { MAX_LABEL_LENGTH } from '../state/selection'

const SEARCH_DEBOUNCE_MS = 350
const MIN_CHARS = 2

function placeLabel(p: Place): string {
  const parts = [p.name, p.admin1 && p.admin1 !== p.name ? p.admin1 : null, p.country].filter(Boolean)
  return parts.join(', ').slice(0, MAX_LABEL_LENGTH)
}

type Status = 'idle' | 'loading' | 'done' | 'error'

export function CitySearch({ onSelect }: { onSelect: (place: Place, label: string) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Place[]>([])
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const [chosen, setChosen] = useState<string | null>(null)
  const listId = useId()
  const wrapRef = useRef<HTMLDivElement>(null)

  const term = query.trim()
  useEffect(() => {
    if (term.length < MIN_CHARS || term === chosen) return
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      setStatus('loading')
      searchPlaces(term, ctrl.signal)
        .then((r) => {
          setResults(r.results)
          setActive(r.results.length ? 0 : -1)
          setStatus('done')
          setError(null)
        })
        .catch((err: unknown) => {
          if ((err as Error).name === 'AbortError') return
          setResults([])
          setStatus('error')
          setError(err instanceof ApiError ? err.message : 'Place search failed. Try again.')
        })
    }, SEARCH_DEBOUNCE_MS)
    return () => {
      clearTimeout(t)
      ctrl.abort()
    }
  }, [term, chosen])

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const tooShort = term.length < MIN_CHARS
  const showList = open && !tooShort && status !== 'idle'

  const choose = (p: Place) => {
    const label = placeLabel(p)
    onSelect(p, label)
    setChosen(label)
    setQuery(label)
    setOpen(false)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && results.length) {
      e.preventDefault()
      setOpen(true)
      setActive((i) => (i + 1) % results.length)
    } else if (e.key === 'ArrowUp' && results.length) {
      e.preventDefault()
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1))
    } else if (e.key === 'Enter' && showList && status === 'done' && results[active]) {
      e.preventDefault()
      choose(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="field city-search" ref={wrapRef}>
      <label htmlFor={`${listId}-input`}>Search city or place</label>
      <div className="city-search-input">
        <Search size={14} aria-hidden />
        <input
          id={`${listId}-input`}
          type="search"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
          placeholder="e.g. Phoenix, Pune, Lagos"
          autoComplete="off"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
            if (e.target.value.trim().length < MIN_CHARS) {
              setStatus('idle')
              setResults([])
            }
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
        {status === 'loading' && <Loader2 size={14} className="spin" aria-label="Searching" />}
        {showList && (
          <ul id={listId} role="listbox" className="city-results" aria-label="Matching places">
            {status === 'loading' && results.length === 0 && <li className="city-empty">Searching…</li>}
            {status === 'done' && results.length === 0 && <li className="city-empty">No places found for “{term}”.</li>}
            {status === 'error' && <li className="city-empty error">{error}</li>}
            {results.map((p, i) => (
              <li
                key={p.id ?? `${p.latitude},${p.longitude}`}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                className={i === active ? 'active' : ''}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault()
                  choose(p)
                }}
              >
                <span>{placeLabel(p)}</span>
                <span className="muted">
                  {p.latitude.toFixed(2)}, {p.longitude.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <span className="fine">Place search by Open-Meteo (GeoNames). Analysis uses the reanalysis grid cell at that point.</span>
    </div>
  )
}
