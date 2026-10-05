import { useEffect, useRef, useState } from 'react'
import { MarkerClusterer } from '@googlemaps/markerclusterer'
import { loadGoogleMaps, MAP_ERROR_EVENT, MAP_ERROR_MESSAGE } from '../api/googleMaps'
import { drawClusteredStops, drawMapOverlays } from '../utils/mapOverlays'
import type { UserPosition } from '../utils/mapOverlays'
import type { BusStop } from '../utils/busStops'

interface Props {
  stops: BusStop[]
  user: UserPosition | null
  selectedCode: string
  onSelect: (stop: BusStop) => void
}

export function BusStopMap({ stops, user, selectedCode, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const select = useRef(onSelect)
  const stopLayer = useRef<ReturnType<typeof drawClusteredStops> | null>(null)
  const [ready, setReady] = useState<{ api: typeof google.maps; map: google.maps.Map } | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { select.current = onSelect }, [onSelect])

  useEffect(() => {
    let cancelled = false
    let authFailed = false
    let instance: google.maps.Map | undefined
    let api: typeof google.maps | undefined
    const authError = () => { authFailed = true; setError(MAP_ERROR_MESSAGE) }
    window.addEventListener(MAP_ERROR_EVENT, authError)
    loadGoogleMaps().then((loaded) => {
      if (cancelled || authFailed || !container.current) return
      api = loaded
      instance = new api.Map(container.current, {
        center: { lat: 1.3521, lng: 103.8198 }, zoom: 11, maxZoom: 18,
        mapId: 'DEMO_MAP_ID', mapTypeId: 'roadmap', tilt: 0,
        streetViewControl: false, mapTypeControl: false, fullscreenControl: true,
        gestureHandling: 'cooperative',
      })
      setReady({ api, map: instance })
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof Error ? reason.message : MAP_ERROR_MESSAGE)
    })
    const element = container.current
    return () => {
      cancelled = true
      window.removeEventListener(MAP_ERROR_EVENT, authError)
      if (instance) api?.event.clearInstanceListeners(instance)
      element?.replaceChildren()
    }
  }, [])

  useEffect(() => {
    if (!ready || error) return
    const layer = drawClusteredStops(ready.api, ready.map, stops, (stop) => select.current(stop),
      (markers) => new MarkerClusterer({ map: ready.map, markers }))
    stopLayer.current = layer
    return () => { layer.dispose(); stopLayer.current = null }
  }, [ready, stops, error])

  useEffect(() => {
    if (!ready || error || !user) return
    return drawMapOverlays(ready.api, ready.map, [], user, '', (stop) => select.current(stop))
  }, [ready, user, stops, error])

  useEffect(() => {
    stopLayer.current?.selectStop(selectedCode)
  }, [ready, stops, user, selectedCode, error])

  return <div className="bus-map-panel">
    {error ? <p className="inline-error" role="alert">{error}</p>
      : !ready && <p role="status">Loading Google map…</p>}
    {!error && <div className="bus-map-toolbar">
      <span>{stops.length.toLocaleString()} stops in the supplied Singapore directory</span>
      <button type="button" className="primary-button" disabled={!ready || stops.length === 0}
        onClick={() => stopLayer.current?.showAll()}>Show all stops</button>
    </div>}
    <div ref={container} className="bus-map-canvas" hidden={Boolean(error)} role="region" aria-label="Google map of bus stops" />
    {!error && <p className="bus-help">{user ? '“You are here” marks your estimated position. Green circle: 500 m. Blue area: location accuracy. ' : 'Search for a stop or use “Find stops within 500 m” to add your location. '}
      All directory stops remain on the map, even when the list is filtered. Click a cluster count to zoom in, then select a stop-code marker to see arrivals. The supplied directory is a snapshot, not a live inventory.</p>}
  </div>
}
