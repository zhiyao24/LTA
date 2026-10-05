export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

export type ConnectionState = 'online' | 'offline' | 'degraded' | 'checking'
export type ContentState = 'ready' | 'loading' | 'empty' | 'offline' | 'error'

export interface BackendStatusResponse {
  backend_status: 'online'
  database_status: 'ready'
  external_api_status: 'not_configured' | 'ready' | 'online' | 'degraded'
  jetson_status: DeviceStatus
  timestamp: string
}

export interface ExternalSnapshotResponse {
  id: number
  source: string
  received_at: string
  data: Record<string, JsonValue>
}

export interface BusEstimate {
  estimated_arrival: string | null
  monitored: boolean | null
  load: 'SEA' | 'SDA' | 'LSD' | null
  wheelchair_accessible: boolean
  vehicle_type: 'SD' | 'DD' | 'BD' | null
}

export interface BusServiceArrival {
  service_no: string
  operator: string
  arrivals: BusEstimate[]
}

export interface BusArrivalResponse {
  source: 'LTA DataMall'
  bus_stop_code: string
  service_no: string | null
  received_at: string
  server_time: string
  refresh_interval_seconds: 20
  is_stale: boolean
  error_message: string | null
  services: BusServiceArrival[]
}

export type DeviceStatus = 'online' | 'offline'

export interface DeviceResponse {
  id: string
  name: string
  transport: string
  status: DeviceStatus
  last_seen_at: string | null
  created_at: string
  heartbeat_timeout_seconds: number
}

export interface DeviceListResponse {
  items: DeviceResponse[]
  count: number
  timestamp: string
}

export interface TelemetryMetrics {
  cpu_temperature_c?: number
  memory_used_percent?: number
  supply_voltage_v?: number
  wifi_signal_dbm?: number
  [key: string]: JsonValue | undefined
}

export interface TelemetryRecordResponse {
  id: number
  device_id: string
  received_at: string
  device_timestamp?: string
  data: TelemetryMetrics
  is_stale: boolean
  stale_after_seconds: number
}

export interface TelemetryHistoryResponse {
  items: TelemetryRecordResponse[]
  count: number
  limit: number
}

export type CommandType = 'STOP' | 'SET_MODE' | 'SET_SPEED' | 'SEND_MESSAGE'

export type CommandStatus =
  | 'pending'
  | 'delivered'
  | 'running'
  | 'completed'
  | 'failed'
  | 'expired'
  | 'cancelled'

export type OperatingMode = 'standby' | 'manual' | 'assisted'

export type CommandDraft =
  | { commandType: 'STOP'; payload: Record<string, never> }
  | { commandType: 'SET_MODE'; payload: { mode: OperatingMode } }
  | { commandType: 'SET_SPEED'; payload: { speed_percent: number } }
  | { commandType: 'SEND_MESSAGE'; payload: { message: string } }

export interface CommandCreateRequest {
  request_id: string
  device_id: string
  command_type: CommandType
  payload: Record<string, JsonValue>
  expires_in_seconds: number
}

export interface CommandResponse {
  id: string
  device_id: string
  command_type: CommandType
  payload: Record<string, JsonValue>
  status: CommandStatus
  created_at: string
  expires_at: string
  acknowledged_at: string | null
  result: Record<string, JsonValue> | null
  simulation_only: true
}

export interface CommandListResponse {
  items: CommandResponse[]
  count: number
}

export interface ApiErrorResponse {
  error: {
    code: string
    message: string
    status: number
  }
  timestamp: string
}

export interface ResourceState<T> {
  state: ContentState
  data: T | null
  errorMessage?: string
}

// Telemetry remains a local mock until its backend endpoint is implemented.
export interface MetricValue {
  id: string
  label: string
  value: string
  unit: string
}

export interface MockTelemetryResponse {
  state: ContentState
  lastReceived: string | null
  isStale: boolean
  staleAfterSeconds: number
  readings: MetricValue[]
  errorMessage?: string
}

// Retained for the telemetry preview fixture while backend migration is gradual.
export type MockScenario =
  | 'ready'
  | 'loading'
  | 'offline'
  | 'stale'
  | 'empty'
  | 'error'

export interface ServiceStatus {
  state: ConnectionState
  detail: string
}

export interface SystemStatusResponse {
  backend: ServiceStatus
  externalApi: ServiceStatus
  jetson: ServiceStatus
  lastHeartbeat: string | null
}

export interface ExternalApiResponse {
  state: ContentState
  source: string | null
  lastUpdated: string | null
  values: MetricValue[]
  errorMessage?: string
}

export interface CommandHistoryItem {
  id: string
  commandType: string
  summary: string
  createdAt: string
  status: CommandStatus
  result: string
}

export interface CommandHistoryResponse {
  state: ContentState
  commands: CommandHistoryItem[]
  errorMessage?: string
}

export interface DashboardResponse {
  system: SystemStatusResponse
  externalApi: ExternalApiResponse
  telemetry: MockTelemetryResponse
  commandHistory: CommandHistoryResponse
}
