import type { BusArrivalResponse } from '../types/api.ts'

export const BUS_REFRESH_MS = 20_000
export const BUS_STALE_MS = 40_000

export function validateBusQuery(busStopCode: string, serviceNo: string): string | null {
  if (!/^[0-9]{5}$/.test(busStopCode)) return 'Enter a five-digit bus stop code, including any leading zero.'
  if (serviceNo && !/^[A-Za-z0-9]{1,10}$/.test(serviceNo)) return 'Enter a service such as 15, 2A or 225G, or leave it blank for all services.'
  return null
}

export function arrivalLabel(estimate: string | null, now: number, stale = false): string {
  if (!estimate || !Number.isFinite(Date.parse(estimate))) return 'No estimate'
  if (stale) return 'Last estimate'
  const seconds = (Date.parse(estimate) - now) / 1000
  if (seconds < 0) return 'Updating…'
  // LTA section 2.1: round down; less than one minute is Arriving.
  if (seconds < 60) return 'Arriving'
  return `${Math.floor(seconds / 60)} min`
}

export function singaporeTime(timestamp: string, includeSeconds = false): string {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore', hour: '2-digit', minute: '2-digit',
    second: includeSeconds ? '2-digit' : undefined, hour12: true,
  }).format(new Date(timestamp))
}

export function busDataIsStale(data: BusArrivalResponse, now: number): boolean {
  return data.is_stale || now - Date.parse(data.received_at) >= BUS_STALE_MS
}
