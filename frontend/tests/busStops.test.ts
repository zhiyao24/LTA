import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { distanceMetres, locationError, nearbyStops, parseBusStops, searchStops } from '../src/utils/busStops.ts'

const stops = parseBusStops(JSON.parse(readFileSync(new URL('../public/BusStops.json', import.meta.url), 'utf8')))

test('supplied directory validates, preserving five digit codes', () => {
  assert.ok(stops.length > 1000)
  assert.ok(stops.some((stop) => stop.BusStopCode === '01059'))
  assert.throws(() => parseBusStops({ value: [{ BusStopCode: 1059 }] }))
  assert.throws(() => parseBusStops({ value: [stops[0], stops[0]] }))
  assert.throws(() => parseBusStops({ value: [{ ...stops[0], Latitude: NaN }] }))
})
test('search is case insensitive and supports code, description and road', () => {
  assert.equal(searchStops(stops, '01059')[0].BusStopCode, '01059')
  assert.ok(searchStops(stops, ' bugis stn ').length >= 2)
  assert.ok(searchStops(stops, 'Victoria St').length > 0)
  assert.equal(searchStops(stops, '').length, 0)
  assert.equal(searchStops(stops, 'not-a-real-stop').length, 0)
})
test('nearby stops are limited to 500 metres and sorted nearest first', () => {
  const origin = stops.find((stop) => stop.BusStopCode === '01059')!
  const results = nearbyStops(stops, origin.Latitude, origin.Longitude)
  assert.equal(results[0].BusStopCode, origin.BusStopCode)
  assert.equal(results[0].distance, 0)
  assert.ok(results.every((stop, i) => stop.distance <= 500 && (!i || stop.distance >= results[i - 1].distance)))
  assert.equal(nearbyStops(stops, 0, 0).length, 0)
  assert.throws(() => nearbyStops(stops, NaN, 0))
})
test('distance calculation and radius boundary are accurate', () => {
  assert.ok(Math.abs(distanceMetres(0, 0, 0, 1) - 111194.93) < 1)
  const origin = { ...stops[0], Latitude: 0, Longitude: 0 }
  const delta = (metres: number) => metres / 6371000 * 180 / Math.PI
  assert.equal(nearbyStops([{ ...origin, Latitude: delta(499.99) }], 0, 0).length, 1)
  assert.equal(nearbyStops([{ ...origin, Latitude: delta(500.01) }], 0, 0).length, 0)
})
test('location failures provide manual-search fallbacks', () => {
  assert.match(locationError(1), /permission was denied/)
  assert.match(locationError(3), /timed out/)
  assert.match(locationError(2), /unavailable/)
})
