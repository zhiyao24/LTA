/// <reference types="google.maps" />
import type { BusStop } from './busStops'

export interface UserPosition { latitude: number; longitude: number; accuracy: number }

export type ClusterFactory = (markers: google.maps.marker.AdvancedMarkerElement[]) => {
  clearMarkers: (noDraw?: boolean) => void
  setMap: (map: google.maps.Map | null) => void
}

// Build the complete directory once. Searching, polling and selecting a stop
// must not recreate thousands of markers or discard stops outside the search.
export function drawClusteredStops(api: typeof google.maps, map: google.maps.Map,
  stops: BusStop[], onSelect: (stop: BusStop) => void,
  clusterFactory: ClusterFactory, doc: Document = document) {
  const bounds = new api.LatLngBounds()
  const listeners: google.maps.MapsEventListener[] = []
  const entries = new Map<string, { stop: BusStop; content: HTMLElement }>()
  let selected = ''
  const markers = stops.map((stop) => {
    const position = { lat: stop.Latitude, lng: stop.Longitude }
    const available = /^\d{5}$/.test(stop.BusStopCode)
    const content = doc.createElement('span')
    content.className = 'stop-map-pin'
    content.textContent = stop.BusStopCode
    entries.set(stop.BusStopCode, { stop, content })
    bounds.extend(position)
    // The clusterer owns visibility; do not attach every marker to the map here.
    const marker = new api.marker.AdvancedMarkerElement({ position, content,
      title: `${stop.Description}, ${stop.BusStopCode}, ${stop.RoadName}. ${available ? 'Show all services' : 'Arrival lookup unavailable'}` })
    if (available) listeners.push(marker.addListener('click', () => onSelect(stop)))
    return marker
  })
  const cluster = clusterFactory(markers)
  const showAll = () => { if (!bounds.isEmpty()) map.fitBounds(bounds, 45) }
  showAll()
  return {
    showAll,
    selectStop(code: string) {
      if (code === selected) return
      const old = entries.get(selected)
      if (old) old.content.className = 'stop-map-pin'
      selected = code
      const entry = entries.get(code)
      if (!entry) return
      entry.content.className = 'stop-map-pin stop-map-pin--selected'
      map.panTo({ lat: entry.stop.Latitude, lng: entry.stop.Longitude })
      map.setZoom(Math.max(17, map.getZoom() ?? 11))
    },
    dispose() {
      cluster.clearMarkers(true)
      cluster.setMap(null)
      listeners.forEach((listener) => listener.remove())
      markers.forEach((marker) => { marker.map = null })
      entries.clear()
    },
  }
}

// Called only after the user opts into Google Maps. Coordinates are given to
// Google's renderer, never to our FastAPI backend or local persistent storage.
export function drawMapOverlays(api: typeof google.maps, map: google.maps.Map,
  stops: BusStop[], user: UserPosition | null, selectedCode: string,
  onSelect: (stop: BusStop) => void, doc: Document = document) {
  const markers: google.maps.marker.AdvancedMarkerElement[] = []
  const listeners: google.maps.MapsEventListener[] = []
  const circles: google.maps.Circle[] = []
  const bounds = new api.LatLngBounds()
  for (const stop of stops) {
    const position = { lat: stop.Latitude, lng: stop.Longitude }
    const available = /^\d{5}$/.test(stop.BusStopCode)
    const content = doc.createElement('span')
    content.className = `stop-map-pin${selectedCode === stop.BusStopCode ? ' stop-map-pin--selected' : ''}`
    content.textContent = stop.BusStopCode // Plain text, never provider-supplied HTML.
    const marker = new api.marker.AdvancedMarkerElement({ map, position, content,
      title: `${stop.Description}, ${stop.BusStopCode}, ${stop.RoadName}. ${available ? 'Show all services' : 'Arrival lookup unavailable'}` })
    if (available) listeners.push(marker.addListener('click', () => onSelect(stop)))
    markers.push(marker)
    bounds.extend(position)
  }
  if (user) {
    const center = { lat: user.latitude, lng: user.longitude }
    const content = doc.createElement('span')
    content.className = 'stop-map-pin stop-map-pin--user'
    content.textContent = 'You are here'
    markers.push(new api.marker.AdvancedMarkerElement({ map, position: center, content,
      title: `Your estimated location, accuracy approximately ${Math.round(user.accuracy)} metres`, zIndex: 1000 }))
    const radius = new api.Circle({ map, center, radius: 500, strokeColor: '#17765a',
      strokeOpacity: 0.8, strokeWeight: 2, fillColor: '#17765a', fillOpacity: 0.07, clickable: false })
    circles.push(radius)
    const radiusBounds = radius.getBounds()
    if (radiusBounds) bounds.union(radiusBounds)
    circles.push(new api.Circle({ map, center, radius: user.accuracy, strokeWeight: 0,
      fillColor: '#2465b0', fillOpacity: 0.12, clickable: false }))
    bounds.extend(center)
  }
  if (!bounds.isEmpty()) map.fitBounds(bounds, 45)
  return () => {
    listeners.forEach((listener) => listener.remove())
    markers.forEach((marker) => { marker.map = null })
    circles.forEach((circle) => circle.setMap(null))
  }
}
