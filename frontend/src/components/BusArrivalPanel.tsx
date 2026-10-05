import { useCallback, useEffect, useRef, useState } from 'react'
import type { Dispatch, FormEvent, SetStateAction } from 'react'
import { ApiClientError, getBusArrivals } from '../api/client'
import { usePolling } from '../hooks/usePolling'
import { BusStopPicker } from './BusStopPicker'
import type { BusStop } from '../utils/busStops'
import type { BusArrivalResponse, BusEstimate, ResourceState } from '../types/api'
import {
  arrivalLabel, BUS_REFRESH_MS, busDataIsStale, singaporeTime, validateBusQuery,
} from '../utils/busArrivals'

interface BusArrivalPanelProps {
  data: ResourceState<BusArrivalResponse>
  onDataChange: Dispatch<SetStateAction<ResourceState<BusArrivalResponse>>>
}

const loads = { SEA: 'Seats available', SDA: 'Standing available', LSD: 'Limited standing' }
const busTypes = { SD: 'Single deck', DD: 'Double deck', BD: 'Bendy bus' }

function ArrivalCard({ bus, index, now, stale }: {
  bus: BusEstimate; index: number; now: number; stale: boolean
}) {
  return (
    <article className={`bus-arrival-card${stale ? ' bus-arrival-card--stale' : ''}`}>
      <span className="bus-arrival-label">{['Next bus', 'Following bus', 'Third bus'][index]}</span>
      <strong className="bus-countdown">{arrivalLabel(bus.estimated_arrival, now, stale)}</strong>
      {bus.estimated_arrival ? (
        <>
          <time className="bus-clock-time" dateTime={bus.estimated_arrival}>
            {singaporeTime(bus.estimated_arrival)} SGT
          </time>
          <span className={`bus-load bus-load--${bus.load ?? 'unknown'}`}>
            {bus.load ? loads[bus.load] : 'Occupancy unavailable'}
          </span>
          <span className="bus-detail">
            {bus.monitored === false ? 'Scheduled estimate' : bus.monitored === true ? 'Location-based estimate' : 'Estimate source unavailable'}
          </span>
          {bus.vehicle_type && <span className="bus-detail">{busTypes[bus.vehicle_type]}</span>}
          {bus.wheelchair_accessible && <span className="bus-detail">Wheelchair accessible</span>}
        </>
      ) : <span className="bus-detail">LTA has no estimate for this bus.</span>}
    </article>
  )
}

export function BusArrivalPanel({ data, onDataChange }: BusArrivalPanelProps) {
  const [busStopCode, setBusStopCode] = useState('')
  const [serviceNo, setServiceNo] = useState('')
  const [selectedStop, setSelectedStop] = useState<BusStop | null>(null)
  const [query, setQuery] = useState<{ stop: string; service: string } | null>(null)
  const [inputError, setInputError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [now, setNow] = useState(Date.now)
  const clockOffset = useRef(0)
  const [paused, setPaused] = useState(document.hidden)
  const queryKey = query ? `${query.stop}:${query.service}` : ''
  const submittedKey = useRef('')

  useEffect(() => {
    let timer: number | undefined
    const update = () => setNow(Date.now() + clockOffset.current)
    const visibility = () => {
      window.clearInterval(timer)
      setPaused(document.hidden)
      update()
      if (!document.hidden) timer = window.setInterval(update, 1000)
    }
    visibility()
    document.addEventListener('visibilitychange', visibility)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [])

  const poll = useCallback(async (signal: AbortSignal) => {
    if (!query) return
    const key = `${query.stop}:${query.service}`
    setIsRefreshing(true)
    try {
      const result = await getBusArrivals(query.stop, query.service, signal)
      if (signal.aborted || submittedKey.current !== key) return
      clockOffset.current = Date.parse(result.server_time) - Date.now()
      setNow(Date.parse(result.server_time))
      onDataChange({
        state: result.is_stale ? 'error' : result.services.length ? 'ready' : 'empty',
        data: result, errorMessage: result.error_message ?? undefined,
      })
    } catch (error) {
      if (signal.aborted || submittedKey.current !== key) return
      onDataChange((current) => ({
        state: error instanceof ApiClientError && error.code === 'network_error' ? 'offline' : 'error',
        data: current.data,
        errorMessage: error instanceof Error ? error.message : 'Could not load bus arrivals.',
      }))
    } finally {
      if (!signal.aborted && submittedKey.current === key) setIsRefreshing(false)
    }
  }, [query, onDataChange])

  usePolling(poll, { enabled: query !== null, intervalMs: BUS_REFRESH_MS, restartKey: queryKey })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const stop = busStopCode.trim()
    const service = serviceNo.trim().toUpperCase()
    const validation = validateBusQuery(stop, service)
    setInputError(validation)
    if (validation) return
    startQuery(stop, service)
  }

  function startQuery(stop: string, service: string) {
    const key = `${stop}:${service}`
    // Updating a search once is enough; repeated clicks cannot create duplicate polls.
    if (submittedKey.current === key) return
    submittedKey.current = key
    onDataChange({ state: 'loading', data: null })
    setQuery({ stop, service })
  }

  const stale = data.data && (
    data.state === 'offline' || data.state === 'error' || busDataIsStale(data.data, now)
  )
  const sameQuery = query !== null && busStopCode.trim() === query.stop && serviceNo.trim().toUpperCase() === query.service

  return (
    <section className="panel external-panel bus-panel" aria-labelledby="bus-arrivals-title">
      <div className="panel-header">
        <div className="panel-heading">
          <h3 id="bus-arrivals-title">Bus arrivals</h3>
          <p>LTA DataMall · Singapore · updates every 20 seconds</p>
        </div>
        <span className="bus-refresh-badge">{paused ? 'Updates paused' : isRefreshing ? 'Updating…' : query ? 'Auto-refresh on' : 'Ready to search'}</span>
      </div>
      <div className="panel-body">
        <BusStopPicker onSelect={(stop) => {
          setSelectedStop(stop)
          setBusStopCode(stop.BusStopCode)
          setServiceNo('')
          setInputError(null)
          startQuery(stop.BusStopCode, '')
        }} />
        <form className="bus-search-form" onSubmit={submit} noValidate>
          <div className="field-group">
            <label className="field-label" htmlFor="bus-stop-code">Bus stop code</label>
            <input id="bus-stop-code" className="text-input" inputMode="numeric"
              value={busStopCode} onChange={(event) => { setBusStopCode(event.target.value); setInputError(null) }}
              placeholder="e.g. 83139" maxLength={5} autoComplete="off" required
              aria-describedby={inputError ? 'bus-search-help bus-search-error' : 'bus-search-help'} aria-invalid={Boolean(inputError)} />
          </div>
          <div className="field-group">
            <label className="field-label" htmlFor="bus-service-no">Service number <span className="bus-optional">(optional)</span></label>
            <input id="bus-service-no" className="text-input" value={serviceNo}
              onChange={(event) => { setServiceNo(event.target.value); setInputError(null) }} placeholder="e.g. 15 or 225G"
              maxLength={10} autoComplete="off" aria-describedby="bus-search-help" />
          </div>
          <button type="submit" className="primary-button" disabled={isRefreshing || sameQuery}>
            {isRefreshing ? 'Loading…' : sameQuery ? 'Tracking arrivals' : 'Show arrivals'}
          </button>
        </form>
        <p className="bus-help" id="bus-search-help">Enter the five-digit code on the bus stop sign. Leave service number blank to see all services.</p>
        {inputError && <p className="inline-error" id="bus-search-error" role="alert">{inputError}</p>}
        <div aria-live="polite" aria-atomic="true" className="bus-search-status">
          {!query && <p className="bus-empty">Where are you heading? Search a bus stop to see the next three arrivals.</p>}
          {data.state === 'loading' && <p className="bus-empty" role="status">Checking arrivals with LTA…</p>}
          {(data.state === 'error' || data.state === 'offline') && (
            <div className="inline-error" role="alert">
              {data.errorMessage} {data.data ? 'Showing the last valid result for this search.' : 'Updates will retry automatically.'}
            </div>
          )}
          {stale && <p className="warning-banner" role="alert">Stale data — these are previous estimates, not live countdowns.</p>}
          {data.data && data.data.services.length === 0 && (
            <p className="bus-empty">No arrival estimates available for stop {data.data.bus_stop_code}{data.data.service_no ? `, service ${data.data.service_no}` : ''}. This does not confirm that the service has stopped operating.</p>
          )}
        </div>
        {data.data && (
          <>
            <div className="bus-results-meta">
              <strong>{selectedStop?.BusStopCode === data.data.bus_stop_code ? `${selectedStop.Description} · ` : ''}Stop {data.data.bus_stop_code}{data.data.service_no ? ` · Service ${data.data.service_no}` : ' · All services'}</strong>
              <span>Last received <time dateTime={data.data.received_at}>{singaporeTime(data.data.received_at, true)}</time> SGT</span>
            </div>
            <div className="bus-services">
              {data.data.services.map((service) => (
                <section className="bus-service" key={service.service_no} aria-label={`Bus service ${service.service_no}`}>
                  <div className="bus-service-heading">
                    <strong className="bus-service-number">{service.service_no}</strong>
                    <span>{service.operator}</span>
                  </div>
                  <div className="bus-arrival-grid">
                    {service.arrivals.map((bus, index) => <ArrivalCard key={index} bus={bus} index={index} now={now} stale={Boolean(stale)} />)}
                  </div>
                </section>
              ))}
            </div>
          </>
        )}
        <p className="bus-footnote">Arrival times are estimates. Automatic refresh pauses when this tab is hidden and resumes when you return.</p>
      </div>
    </section>
  )
}
