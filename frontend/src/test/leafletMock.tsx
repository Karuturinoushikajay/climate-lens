import type { ReactNode } from 'react'

type ClickHandler = (e: { latlng: { lat: number; lng: number } }) => void

export const mapState: { click: ClickHandler | null } = { click: null }

export function mapClick(lat: number, lng: number) {
  if (!mapState.click) throw new Error('map click handler not registered')
  mapState.click({ latlng: { lat, lng } })
}

const fakeMap = { setView: () => undefined, fitBounds: () => undefined, getZoom: () => 6 }

export const leafletMock = {
  MapContainer: ({ children }: { children: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  CircleMarker: ({ children, center }: { children?: ReactNode; center: [number, number] }) => (
    <div data-testid="marker" data-center={center.join(',')}>
      {children}
    </div>
  ),
  Rectangle: ({ children, bounds }: { children?: ReactNode; bounds: [number, number][] }) => (
    <div data-testid="rectangle" data-bounds={bounds.flat().join(',')}>
      {children}
    </div>
  ),
  Tooltip: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
  useMap: () => fakeMap,
  useMapEvents: (handlers: { click: ClickHandler }) => {
    mapState.click = handlers.click
    return fakeMap
  },
}
