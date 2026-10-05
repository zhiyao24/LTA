export interface BusStop {
  BusStopCode: string
  Description: string
  RoadName: string
  Latitude: number
  Longitude: number
}

export function parseBusStops(value: unknown): BusStop[] {
  if (!value || typeof value !== 'object' || !('value' in value) || !Array.isArray(value.value)) {
    throw new Error('The bus-stop directory is unavailable.')
  }
  const seen = new Set<string>()
  return value.value.map((stop: BusStop) => {
    if (!stop || !/^[A-Z0-9]{5}$/.test(stop.BusStopCode) || typeof stop.BusStopCode !== 'string'
      || typeof stop.Description !== 'string' || typeof stop.RoadName !== 'string'
      || !validCoordinates(stop.Latitude, stop.Longitude) || seen.has(stop.BusStopCode)) {
      throw new Error('The bus-stop directory contains invalid records.')
    }
    seen.add(stop.BusStopCode)
    return stop
  })
}

export function validCoordinates(latitude: number, longitude: number): boolean {
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180
}

export function distanceMetres(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const radians = Math.PI / 180
  const a = Math.sin((lat2 - lat1) * radians / 2) ** 2
    + Math.cos(lat1 * radians) * Math.cos(lat2 * radians) * Math.sin((lon2 - lon1) * radians / 2) ** 2
  return 6371000 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, a))))
}

export function searchStops(stops: BusStop[], query: string): BusStop[] {
  const term = query.trim().toLowerCase()
  if (!term) return []
  return stops.filter((stop) => `${stop.BusStopCode} ${stop.Description} ${stop.RoadName}`.toLowerCase().includes(term))
    .sort((a, b) => Number(b.BusStopCode === term) - Number(a.BusStopCode === term)
      || a.Description.localeCompare(b.Description) || a.BusStopCode.localeCompare(b.BusStopCode))
}

export function nearbyStops(stops: BusStop[], latitude: number, longitude: number) {
  if (!validCoordinates(latitude, longitude)) throw new Error('Your location could not be determined. Please search by name or code.')
  return stops.map((stop) => ({ ...stop, distance: distanceMetres(latitude, longitude, stop.Latitude, stop.Longitude) }))
    .filter((stop) => stop.distance <= 500)
    .sort((a, b) => a.distance - b.distance || a.BusStopCode.localeCompare(b.BusStopCode))
}

export function locationError(code: number): string {
  if (code === 1) return 'Location permission was denied. Allow location in browser settings or search by name/code.'
  if (code === 3) return 'Location request timed out. Try again or search by name/code.'
  return 'Your location is unavailable. Try again or search by name/code.'
}
