import { useEffect, useMemo, useRef, useState } from 'react'
import { BusStopMap } from './BusStopMap'
import type { UserPosition } from '../utils/mapOverlays'
import { locationError, nearbyStops, parseBusStops, searchStops } from '../utils/busStops'
import type { BusStop } from '../utils/busStops'

export function BusStopPicker({ onSelect }: { onSelect: (stop: BusStop) => void }) {
  const [stops, setStops] = useState<BusStop[]>([])
  const [loadError, setLoadError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [nearby, setNearby] = useState<ReturnType<typeof nearbyStops> | null>(null)
  const [locating, setLocating] = useState(false)
  const [message, setMessage] = useState('')
  const [accuracy, setAccuracy] = useState<number | null>(null)
  const [userPosition, setUserPosition] = useState<UserPosition | null>(null)
  const [showMap, setShowMap] = useState(false)
  const [selectedStop, setSelectedStop] = useState<BusStop | null>(null)
  const locationRequest = useRef(0)
  const busy = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${import.meta.env.BASE_URL}BusStops.json`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error('Could not load the bus-stop directory.')
        return parseBusStops(await response.json())
      })
      .then((result) => { if (!controller.signal.aborted) setStops(result) })
      .catch(() => { if (!controller.signal.aborted) setLoadError('Could not load the bus-stop directory. Retry or use the stop-code field below.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [attempt])

  useEffect(() => () => { locationRequest.current += 1 }, [])

  function findNearby() {
    if (busy.current) return
    setMessage('')
    if (!window.isSecureContext) {
      setMessage('Location requires trusted HTTPS on other devices. Use the Mac’s HTTPS address on port 5443 after installing its public CA certificate (see docs/local-https.md). On this Mac, localhost also works. You can still search by name/code here.')
      return
    }
    if (!navigator.geolocation) { setMessage('This browser does not support location. Search by name/code instead.'); return }
    busy.current = true
    setLocating(true)
    setNearby(null)
    setAccuracy(null)
    setUserPosition(null)
    const request = ++locationRequest.current
    navigator.geolocation.getCurrentPosition((position) => {
      if (request !== locationRequest.current) return
      try {
        setNearby(nearbyStops(stops, position.coords.latitude, position.coords.longitude))
        setAccuracy(position.coords.accuracy)
        setUserPosition({ latitude: position.coords.latitude, longitude: position.coords.longitude, accuracy: position.coords.accuracy })
        setSearch('')
      } catch (error) { setMessage(error instanceof Error ? error.message : 'Location unavailable.') }
      busy.current = false
      setLocating(false)
    }, (error) => {
      if (request !== locationRequest.current) return
      busy.current = false
      setLocating(false)
      setMessage(locationError(error.code))
    }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 })
  }

  const matches = useMemo(() => nearby ?? searchStops(stops, search), [nearby, stops, search])
  const visible = useMemo(() => nearby ? matches : matches.slice(0, 30), [nearby, matches])
  function choose(stop: BusStop) {
    setSelectedStop(stop)
    onSelect(stop)
  }
  return <div className="stop-picker">
    <label className="field-label" htmlFor="stop-search">Find a bus stop by description or code</label>
    <div className="stop-search-row">
      <input id="stop-search" className="text-input" value={search} placeholder="e.g. Bugis Stn or 01059"
        aria-describedby="stop-picker-help" maxLength={100} disabled={locating}
        onChange={(event) => { setSearch(event.target.value); setNearby(null); setAccuracy(null); setMessage('') }} />
      <button type="button" className="primary-button" disabled={loading || Boolean(loadError) || locating} onClick={findNearby}>
        {locating ? 'Finding your location…' : 'Find stops within 500 m'}
      </button>
    </div>
    <p className="bus-help" id="stop-picker-help">Choose a stop to show all its services. Nearby search asks permission. We do not save your location or send it to our backend. If you enable Google Maps, your location is provided to Google's map renderer.</p>
    <div role="status">
      {loading && <p>Loading bus-stop directory…</p>}
      {loadError && <p className="inline-error">{loadError} <button type="button" onClick={() => { setLoading(true); setLoadError(''); setAttempt((value) => value + 1) }}>Retry directory</button></p>}
      {message && <p className="warning-banner">{message}</p>}
      {accuracy !== null && <p className="bus-help">Location accuracy: approximately ±{Math.round(accuracy)} m. Distances are straight-line, not walking distances.{accuracy > 100 ? ' Location is imprecise; some nearby stops may be missed.' : ''}</p>}
      {!loading && !loadError && (nearby !== null || search.trim()) && <p className="bus-help">
        {matches.length === 0 ? 'No stops found. Try another name/code or check your location.' : nearby ? `${matches.length} stops within 500 m, nearest first.` : `${matches.length} matching stops.${matches.length > 30 ? ' Showing the first 30; refine your search.' : ''}`}
      </p>}
    </div>
    <div className="bus-map-consent">
      <button type="button" className="primary-button" aria-expanded={showMap} aria-controls="optional-stop-map"
        onClick={() => setShowMap((current) => !current)}>{showMap ? 'Hide Google map' : 'Show Google map'}</button>
      <p className="bus-help">Optional: enabling the map contacts Google and displays your location if shared. Google receives map requests and the viewed area. Internet is required; name/code search works without Google. Hiding the map does not unload Google's script; reload the page to reset.</p>
    </div>
    <div id="optional-stop-map">
      {showMap && <BusStopMap stops={stops} user={userPosition} selectedCode={selectedStop?.BusStopCode ?? ''} onSelect={choose} />}
    </div>
    {selectedStop && <p role="status" className="bus-selected-stop">Selected: {selectedStop.Description} · {selectedStop.BusStopCode}. Arrivals appear below the stop list.</p>}
    {visible.length > 0 && <ul className="stop-results" aria-label={nearby ? 'Nearby bus stops, nearest first' : 'Matching bus stops'}>
      {visible.map((stop) => <li key={stop.BusStopCode}>
        <button type="button" aria-pressed={selectedStop?.BusStopCode === stop.BusStopCode} disabled={!/^\d{5}$/.test(stop.BusStopCode)} onClick={() => choose(stop)}>
          <span><strong>{stop.Description}</strong><span className="bus-detail">{stop.BusStopCode} · {stop.RoadName}</span></span>
          <span>{'distance' in stop ? `${Math.round(Number(stop.distance))} m · ` : ''}{/^\d{5}$/.test(stop.BusStopCode) ? 'Show all services →' : 'Arrival lookup unavailable for this code'}</span>
        </button>
      </li>)}
    </ul>}
  </div>
}
