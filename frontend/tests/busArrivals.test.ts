import assert from 'node:assert/strict'
import test from 'node:test'
import { arrivalLabel, busDataIsStale, singaporeTime, validateBusQuery } from '../src/utils/busArrivals.ts'
import type { BusArrivalResponse } from '../src/types/api.ts'

const now = Date.parse('2026-09-24T10:00:00Z')

test('stop codes preserve leading zeros and service identifiers can contain letters', () => {
  assert.equal(validateBusQuery('01219', '225G'), null)
  assert.equal(validateBusQuery('83139', '2A'), null)
  assert.equal(validateBusQuery('83139', ''), null)
  assert.ok(validateBusQuery('1219', '15'))
  assert.ok(validateBusQuery('83139', '15;ls'))
})

test('LTA durations round down and under one minute displays Arriving', () => {
  assert.equal(arrivalLabel('2026-09-24T18:03:49+08:00', now), '3 min')
  assert.equal(arrivalLabel('2026-09-24T18:01:59+08:00', now), '1 min')
  assert.equal(arrivalLabel('2026-09-24T18:00:59+08:00', now), 'Arriving')
})

test('missing, expired and stale estimates never become a false live zero', () => {
  assert.equal(arrivalLabel(null, now), 'No estimate')
  assert.equal(arrivalLabel('', now), 'No estimate')
  assert.equal(arrivalLabel('bad data', now), 'No estimate')
  assert.equal(arrivalLabel('2026-09-24T09:59:59Z', now), 'Updating…')
  assert.equal(arrivalLabel('2026-09-24T10:03:00Z', now, true), 'Last estimate')
})

test('times are displayed in Singapore regardless of the viewers timezone', () => {
  assert.match(singaporeTime('2026-09-24T10:03:00Z'), /06:03\s?pm/i)
})

test('missed refreshes and backend stale flags mark results stale', () => {
  const data: BusArrivalResponse = {
    source: 'LTA DataMall', bus_stop_code: '01219', service_no: null,
    received_at: '2026-09-24T10:00:00Z', server_time: '2026-09-24T10:00:00Z',
    refresh_interval_seconds: 20, is_stale: false, error_message: null, services: [],
  }
  assert.equal(busDataIsStale(data, now + 39_999), false)
  assert.equal(busDataIsStale(data, now + 40_000), true)
  assert.equal(busDataIsStale({ ...data, is_stale: true }, now), true)
})
