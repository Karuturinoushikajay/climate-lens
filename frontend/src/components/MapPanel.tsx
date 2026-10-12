import { useEffect, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Rectangle, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { MousePointerClick, Square } from 'lucide-react'
import { normalizeBox, round4, type Location } from '../state/selection'

export type SelectMode = 'point' | 'box'

// Keyless providers only; both require visible attribution and permit light, non-bulk use.
const TILE_PROVIDERS = [
  {
    name: 'OpenStreetMap',
    url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
  {
    name: 'OpenTopoMap',
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution:
      'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM | Style &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
    maxZoom: 17,
  },
]
const TILE_ERROR_LIMIT = 6

interface Props {
  location: Location
  label: string
  mode: SelectMode
  onModeChange: (mode: SelectMode) => void
  onSelect: (location: Location) => void
  focusToken: number
  disabled?: boolean
}

function ClickHandler({
  mode,
  onSelect,
  pendingCorner,
  setPendingCorner,
  disabled,
}: {
  mode: SelectMode
  onSelect: (l: Location) => void
  pendingCorner: [number, number] | null
  setPendingCorner: (c: [number, number] | null) => void
  disabled?: boolean
}) {
  useMapEvents({
    click(e) {
      if (disabled) return
      const lat = round4(e.latlng.lat)
      const lng = round4(((((e.latlng.lng + 180) % 360) + 360) % 360) - 180)
      if (mode === 'point') {
        onSelect({ kind: 'point', latitude: lat, longitude: lng })
      } else if (!pendingCorner) {
        setPendingCorner([lat, lng])
      } else {
        onSelect(normalizeBox(pendingCorner, [lat, lng]))
        setPendingCorner(null)
      }
    },
  })
  return null
}

// Leaflet measures its container once; re-measure when the layout around it changes height.
function SizeWatcher({ mode }: { mode: SelectMode }) {
  const map = useMap()
  useEffect(() => {
    const el = map.getContainer()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => map.invalidateSize())
    ro.observe(el)
    return () => ro.disconnect()
  }, [map])
  useEffect(() => {
    const id = requestAnimationFrame(() => map.invalidateSize())
    return () => cancelAnimationFrame(id)
  }, [map, mode])
  return null
}

function FocusController({ location, focusToken }: { location: Location; focusToken: number }) {
  const map = useMap()
  const last = useRef(-1)
  useEffect(() => {
    if (focusToken === last.current) return
    last.current = focusToken
    if (location.kind === 'point') map.setView([location.latitude, location.longitude], Math.max(map.getZoom(), 7))
    else
      map.fitBounds(
        [
          [location.south, location.west],
          [location.north, location.east],
        ],
        { padding: [20, 20] },
      )
  }, [focusToken, location, map])
  return null
}

export function MapPanel({ location, label, mode, onModeChange, onSelect, focusToken, disabled }: Props) {
  const [providerIndex, setProviderIndex] = useState(0)
  const [tilesFailed, setTilesFailed] = useState(false)
  const [pendingCorner, setPendingCorner] = useState<[number, number] | null>(null)
  const errors = useRef(0)
  const provider = TILE_PROVIDERS[providerIndex]

  const onTileError = () => {
    errors.current += 1
    if (errors.current < TILE_ERROR_LIMIT) return
    errors.current = 0
    if (providerIndex + 1 < TILE_PROVIDERS.length) setProviderIndex(providerIndex + 1)
    else setTilesFailed(true)
  }

  const center: [number, number] =
    location.kind === 'point'
      ? [location.latitude, location.longitude]
      : [(location.south + location.north) / 2, (location.west + location.east) / 2]

  return (
    <section className="panel map-panel" aria-label="Region map">
      <div className="panel-head">
        <h2>Select a region</h2>
        <div className="segmented" role="group" aria-label="Map selection mode">
          <button
            type="button"
            className={mode === 'point' ? 'active' : ''}
            aria-pressed={mode === 'point'}
            onClick={() => {
              setPendingCorner(null)
              onModeChange('point')
            }}
          >
            <MousePointerClick size={14} aria-hidden /> Point
          </button>
          <button
            type="button"
            className={mode === 'box' ? 'active' : ''}
            aria-pressed={mode === 'box'}
            onClick={() => {
              setPendingCorner(null)
              onModeChange('box')
            }}
          >
            <Square size={14} aria-hidden /> Lat-lon box
          </button>
        </div>
      </div>
      <p className="hint">
        {mode === 'point'
          ? 'Click the map to choose a point.'
          : pendingCorner
            ? `First corner set at ${pendingCorner[0].toFixed(2)}, ${pendingCorner[1].toFixed(2)}. Click the opposite corner.`
            : 'Click two opposite corners to draw a box (max 10° per side).'}
      </p>
      <div className="map-wrap">
        <MapContainer center={center} zoom={6} scrollWheelZoom className="map" worldCopyJump>
          {!tilesFailed && (
            <TileLayer
              key={provider.url}
              url={provider.url}
              attribution={provider.attribution}
              maxZoom={provider.maxZoom}
              className="tiles-dark"
              eventHandlers={{ tileerror: onTileError }}
            />
          )}
          <ClickHandler
            mode={mode}
            onSelect={onSelect}
            pendingCorner={pendingCorner}
            setPendingCorner={setPendingCorner}
            disabled={disabled}
          />
          <FocusController location={location} focusToken={focusToken} />
          <SizeWatcher mode={mode} />
          {location.kind === 'point' ? (
            <CircleMarker
              center={[location.latitude, location.longitude]}
              radius={9}
              pathOptions={{ color: '#f2b14c', fillColor: '#f2b14c', fillOpacity: 0.7, weight: 2 }}
            >
              <Tooltip direction="top" offset={[0, -8]}>
                {label || 'Selected point'}
              </Tooltip>
            </CircleMarker>
          ) : (
            <Rectangle
              bounds={[
                [location.south, location.west],
                [location.north, location.east],
              ]}
              pathOptions={{ color: '#f2b14c', weight: 2, fillOpacity: 0.12 }}
            >
              <Tooltip sticky>{label || 'Selected box'}</Tooltip>
            </Rectangle>
          )}
          {pendingCorner && (
            <CircleMarker center={pendingCorner} radius={5} pathOptions={{ color: '#8fe3c8', fillOpacity: 1 }} />
          )}
        </MapContainer>
        {tilesFailed && (
          <div className="map-fallback" role="status">
            Map tiles could not be loaded. You can still click the map or enter coordinates manually.
          </div>
        )}
      </div>
      <p className="fine">
        Basemap: {tilesFailed ? 'unavailable' : provider.name}. A point query represents one reanalysis grid cell,
        not a whole city or administrative area.
      </p>
    </section>
  )
}
