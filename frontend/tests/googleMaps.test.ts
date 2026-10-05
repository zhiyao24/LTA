import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { createMapsLoader, MAP_ERROR_EVENT } from '../src/api/googleMaps.ts'
import { drawClusteredStops, drawMapOverlays } from '../src/utils/mapOverlays.ts'
import { parseBusStops } from '../src/utils/busStops.ts'
import type { BusStop } from '../src/utils/busStops.ts'

function loaderFixture(timeout = 1000) {
  const host = Object.assign(new EventTarget(), {
    google: { maps: { Map: class {}, marker: { AdvancedMarkerElement: class {} } } },
    ltaMapsReady: undefined as (() => void) | undefined,
    gm_authFailure: undefined as (() => void) | undefined,
  })
  const scripts: Array<{ src: string; onerror: () => void }> = []
  const doc = { createElement: () => ({}), head: { appendChild: (script: typeof scripts[number]) => scripts.push(script) } }
  return { host, scripts, load: createMapsLoader(host as unknown as Window, doc as unknown as Document, timeout) }
}

test('all directory stops enter clustering; selecting never rebuilds markers; teardown removes everything', () => {
  const stops = parseBusStops(JSON.parse(readFileSync(new URL('../public/BusStops.json', import.meta.url), 'utf8')))
  const markers: FakeMarker[] = []
  let removed = 0
  let fitted = 0
  let selected = ''
  let zoom = 11
  let clustered = 0
  let cleared = false
  let detached = false
  class FakeMarker {
    map: unknown
    content: HTMLElement
    click?: () => void
    constructor(options: { content: HTMLElement; map?: unknown }) {
      this.map = options.map; this.content = options.content; markers.push(this)
    }
    addListener(_name: string, fn: () => void) { this.click = fn; return { remove: () => { removed++ } } }
  }
  class FakeBounds {
    length = 0
    extend() { this.length++ }
    isEmpty() { return this.length === 0 }
  }
  const api = { marker: { AdvancedMarkerElement: FakeMarker }, LatLngBounds: FakeBounds }
  const map = { fitBounds: () => { fitted++ }, panTo: () => {}, getZoom: () => zoom, setZoom: (value: number) => { zoom = value } }
  const doc = { createElement: () => ({ className: '', textContent: '' }) }
  const layer = drawClusteredStops(api as unknown as typeof google.maps, map as unknown as google.maps.Map,
    stops, (stop) => { selected = stop.BusStopCode }, (items) => {
      clustered = items.length
      return { clearMarkers: () => { cleared = true }, setMap: (value) => { detached = value === null } }
    }, doc as unknown as Document)
  assert.equal(clustered, 4976)
  assert.equal(new Set(markers.map((marker) => marker.content.textContent)).size, stops.length)
  assert.ok(markers.every((marker) => marker.map === undefined))
  const stop = stops.findIndex((entry) => entry.BusStopCode === '01059')
  markers[stop].click!()
  assert.equal(selected, '01059')
  layer.selectStop(selected)
  assert.equal(zoom, 17)
  assert.match(markers[stop].content.className, /selected/)
  layer.selectStop(stops[0].BusStopCode)
  assert.equal(markers[stop].content.className, 'stop-map-pin')
  assert.equal(markers.length, stops.length)
  layer.showAll()
  assert.equal(fitted, 2)
  layer.dispose()
  assert.equal(removed, stops.filter((entry) => /^\d{5}$/.test(entry.BusStopCode)).length)
  assert.ok(cleared && detached)
  assert.ok(markers.every((marker) => marker.map === null))
})

test('no map request before opt-in; absent key does not load Google', async () => {
  const { load, scripts } = loaderFixture()
  assert.equal(scripts.length, 0)
  await assert.rejects(load(''), /not configured/)
  assert.equal(scripts.length, 0)
})

test('map loads once, coalesces concurrent callers and uses fixed HTTPS Google endpoint', async () => {
  const { load, scripts, host } = loaderFixture()
  const first = load('test-browser-key')
  assert.equal(first, load('test-browser-key'))
  assert.equal(scripts.length, 1)
  const url = new URL(scripts[0].src)
  assert.equal(url.origin, 'https://maps.googleapis.com')
  assert.equal(url.searchParams.get('libraries'), 'maps,marker')
  host.ltaMapsReady!()
  assert.equal(await first, host.google.maps)
  assert.equal(load('test-browser-key'), first)
})

test('network failure is friendly, hides key, and never retries automatically', async () => {
  const { load, scripts } = loaderFixture()
  const promise = load('test-browser-key')
  scripts[0].onerror()
  await assert.rejects(promise, (error: Error) => error.message.includes('stop list still works') && !error.message.includes('test-browser-key'))
  await assert.rejects(load('test-browser-key'), /could not load/)
  assert.equal(scripts.length, 1)
})

test('timeout is bounded; authentication errors before and after readiness are reported', async () => {
  const timed = loaderFixture(5)
  await assert.rejects(timed.load('test-browser-key'), /could not load/)
  const fixture = loaderFixture()
  const pending = fixture.load('test-browser-key')
  fixture.host.gm_authFailure!()
  await assert.rejects(pending, /could not load/)
  const late = loaderFixture()
  let errors = 0
  late.host.addEventListener(MAP_ERROR_EVENT, () => { errors++ })
  const ready = late.load('test-browser-key')
  late.host.ltaMapsReady!()
  await ready
  late.host.gm_authFailure!()
  assert.equal(errors, 1)
  await assert.rejects(late.load('test-browser-key'), /could not load/)
})

test('map overlays show user, 500 m and accuracy circles; marker selection and cleanup work', () => {
  const markers: FakeMarker[] = []
  const circles: FakeCircle[] = []
  let removed = 0
  let fitted = 0
  class FakeMarker {
    map: unknown
    title: string
    click?: () => void
    constructor(options: { map: unknown; title: string }) { this.map = options.map; this.title = options.title; markers.push(this) }
    addListener(_name: string, action: () => void) { this.click = action; return { remove: () => { removed++ } } }
  }
  class FakeCircle {
    radius: number
    map: unknown
    constructor(options: { map: unknown; radius: number }) { this.map = options.map; this.radius = options.radius; circles.push(this) }
    getBounds() { return {} }
    setMap(map: unknown) { this.map = map }
  }
  class FakeBounds {
    length = 0
    extend() { this.length++ }
    union() {}
    isEmpty() { return this.length === 0 }
  }
  const api = { marker: { AdvancedMarkerElement: FakeMarker }, Circle: FakeCircle, LatLngBounds: FakeBounds }
  const map = { fitBounds: () => { fitted++ } }
  const doc = { createElement: () => ({ className: '', textContent: '' }) }
  const stop: BusStop = { BusStopCode: '01059', Description: 'Bugis Stn', RoadName: 'Victoria St', Latitude: 1.30, Longitude: 103.85 }
  let selected = ''
  const cleanup = drawMapOverlays(api as unknown as typeof google.maps, map as unknown as google.maps.Map,
    [stop, { ...stop, BusStopCode: 'N4401' }], { latitude: 1.3, longitude: 103.85, accuracy: 20 }, '',
    (value) => { selected = value.BusStopCode }, doc as unknown as Document)
  assert.equal(markers.length, 3)
  assert.deepEqual(circles.map((circle) => circle.radius), [500, 20])
  assert.match(markers[2].title, /Your estimated location/)
  assert.equal(markers[1].click, undefined)
  markers[0].click!()
  assert.equal(selected, '01059')
  assert.equal(fitted, 1)
  cleanup()
  assert.equal(removed, 1)
  assert.ok(markers.every((marker) => marker.map === null))
  assert.ok(circles.every((circle) => circle.map === null))
})
