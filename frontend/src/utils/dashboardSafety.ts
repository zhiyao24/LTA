import type {
  ConnectionState,
  DeviceListResponse,
  DeviceResponse,
  ResourceState,
  TelemetryMetrics,
  TelemetryRecordResponse,
} from '../types/api.ts'

export interface JetsonDisplayStatus {
  detail: string
  state: ConnectionState
}

export interface VisibleTelemetryMetric {
  key: string
  label: string
  unit: string
  value: number
}

const metricDefinitions = [
  { key: 'cpu_temperature_c', label: 'CPU temperature', unit: '°C' },
  { key: 'memory_used_percent', label: 'Memory use', unit: '%' },
  { key: 'supply_voltage_v', label: 'Supply voltage', unit: 'V' },
  { key: 'wifi_signal_dbm', label: 'Wi-Fi signal', unit: 'dBm' },
] as const

function formatHeartbeat(timestamp: string | null) {
  if (!timestamp) return 'No heartbeat received'
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

export function selectedDevice(
  devices: ResourceState<DeviceListResponse>,
  selectedDeviceId: string,
): DeviceResponse | null {
  return devices.data?.items.find(
    (device) => device.id === selectedDeviceId.trim(),
  ) ?? null
}

export function deriveJetsonDisplayStatus(
  devices: ResourceState<DeviceListResponse>,
  selectedDeviceId: string,
): JetsonDisplayStatus {
  const device = selectedDevice(devices, selectedDeviceId)
  if (!selectedDeviceId.trim()) {
    return { state: 'degraded', detail: 'Enter a device ID to monitor its heartbeat' }
  }
  if (devices.state === 'loading') {
    return { state: 'checking', detail: 'Checking the latest heartbeat' }
  }
  if (devices.state === 'error' || devices.state === 'offline') {
    return {
      state: 'offline',
      detail: devices.errorMessage ?? 'Device status could not be loaded',
    }
  }
  if (devices.state === 'empty' && devices.errorMessage) {
    return { state: 'degraded', detail: devices.errorMessage }
  }
  if (!device) {
    return { state: 'offline', detail: 'No heartbeat has registered this device yet' }
  }
  return {
    state: device.status,
    detail: `${device.status === 'online' ? 'Last heartbeat' : 'Heartbeat timed out; last received'} ${formatHeartbeat(device.last_seen_at)}`,
  }
}

export function visibleTelemetryMetrics(
  data: TelemetryMetrics | undefined,
): VisibleTelemetryMetric[] {
  return metricDefinitions.flatMap((definition) => {
    const value = data?.[definition.key]
    return typeof value === 'number' ? [{ ...definition, value }] : []
  })
}

export function telemetrySafetyState(
  device: DeviceResponse | null,
  telemetry: ResourceState<TelemetryRecordResponse>,
) {
  return {
    deviceOffline: device?.status === 'offline',
    stale: telemetry.data?.is_stale === true,
  }
}
