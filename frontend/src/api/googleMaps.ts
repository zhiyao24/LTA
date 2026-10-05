/// <reference types="google.maps" />

export const MAP_ERROR_EVENT = 'lta-google-map-error'
export const MAP_ERROR_MESSAGE = 'Google Maps could not load. Check internet access, the map key, allowed website addresses and demo quota. The stop list still works. Reload the page to try again.'

type MapsWindow = Window & {
  google?: { maps: typeof google.maps }
  ltaMapsReady?: () => void
  gm_authFailure?: () => void
}

// One load per page, including React StrictMode and repeated show/hide actions.
// A failed load stays failed until reload: no unlimited retries or duplicate scripts.
export function createMapsLoader(host: MapsWindow, doc: Document, timeoutMs = 15000) {
  let pending: Promise<typeof google.maps> | undefined
  let failed = false
  return (key: string): Promise<typeof google.maps> => {
    if (failed) return Promise.reject(new Error(MAP_ERROR_MESSAGE))
    if (pending) return pending
    if (!key.trim()) return Promise.reject(new Error('Google Maps is not configured. Set VITE_GOOGLE_MAPS_API_KEY in frontend/.env.local and restart Vite.'))
    pending = new Promise((resolve, reject) => {
      let settled = false
      const script = doc.createElement('script')
      const fail = () => {
        failed = true
        host.dispatchEvent(new Event(MAP_ERROR_EVENT))
        if (settled) return
        settled = true
        clearTimeout(timer)
        reject(new Error(MAP_ERROR_MESSAGE))
      }
      const timer = setTimeout(fail, timeoutMs)
      host.gm_authFailure = fail // Google may report authentication failure after its callback.
      host.ltaMapsReady = () => {
        if (settled) return
        if (!host.google?.maps?.Map || !host.google.maps.marker?.AdvancedMarkerElement) { fail(); return }
        settled = true
        clearTimeout(timer)
        resolve(host.google.maps)
      }
      const url = new URL('https://maps.googleapis.com/maps/api/js')
      url.search = new URLSearchParams({ key: key.trim(), loading: 'async', callback: 'ltaMapsReady', libraries: 'maps,marker', v: 'weekly', region: 'SG', language: 'en' }).toString()
      script.src = url.toString()
      script.async = true
      script.onerror = fail
      doc.head.appendChild(script)
    })
    return pending
  }
}

let loader: ReturnType<typeof createMapsLoader> | undefined
export function loadGoogleMaps(): Promise<typeof google.maps> {
  loader ??= createMapsLoader(window, document)
  return loader(import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? '')
}
