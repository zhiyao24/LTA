import assert from 'node:assert/strict'
import test from 'node:test'

import {
  deriveJetsonDisplayStatus,
  telemetrySafetyState,
  visibleTelemetryMetrics,
} from '../src/utils/dashboardSafety.ts'
import type {
  DeviceListResponse,
  DeviceResponse,
  ResourceState,
  TelemetryRecordResponse,
} from '../src/types/api.ts'


const device: DeviceResponse = {
  id: 'jetson-simulator',
  name: 'jetson-simulator',
  transport: 'wifi',
  status: 'offline',
  last_seen_at: '2026-09-03T08:00:00+00:00',
  created_at: '2026-09-03T07:00:00+00:00',
  heartbeat_timeout_seconds: 10,
}

function deviceState(item: DeviceResponse): ResourceState<DeviceListResponse> {
  return {
    state: 'ready',
    data: {
      items: [item],
      count: 1,
      timestamp: '2026-09-03T08:00:11+00:00',
    },
  }
}

test('offline heartbeat state is presented as offline with timeout text', () => {
  const status = deriveJetsonDisplayStatus(
    deviceState(device),
    'jetson-simulator',
  )

  assert.equal(status.state, 'offline')
  assert.match(status.detail, /Heartbeat timed out/)
})

test('network errors remain offline even when an old online device is cached', () => {
  const status = deriveJetsonDisplayStatus(
    {
      ...deviceState({ ...device, status: 'online' }),
      state: 'offline',
      errorMessage: 'Backend unavailable',
    },
    'jetson-simulator',
  )

  assert.deepEqual(status, { state: 'offline', detail: 'Backend unavailable' })
})

test('stale telemetry and device loss drive both frontend warnings', () => {
  const telemetry: ResourceState<TelemetryRecordResponse> = {
    state: 'ready',
    data: {
      id: 1,
      device_id: device.id,
      received_at: '2026-09-03T08:00:00+00:00',
      device_timestamp: '2026-09-03T07:59:59+00:00',
      data: { cpu_temperature_c: 44.5 },
      is_stale: true,
      stale_after_seconds: 10,
    },
  }

  assert.deepEqual(telemetrySafetyState(device, telemetry), {
    deviceOffline: true,
    stale: true,
  })
})

test('missing telemetry is omitted while a real zero remains visible', () => {
  const readings = visibleTelemetryMetrics({
    memory_used_percent: 0,
    cpu_temperature_c: undefined,
  })

  assert.deepEqual(
    readings.map(({ key, value }) => ({ key, value })),
    [{ key: 'memory_used_percent', value: 0 }],
  )
})
