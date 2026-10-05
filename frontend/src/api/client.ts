import type {
  ApiErrorResponse,
  BackendStatusResponse,
  BusArrivalResponse,
  CommandCreateRequest,
  CommandListResponse,
  CommandResponse,
  DeviceListResponse,
  ExternalSnapshotResponse,
  TelemetryHistoryResponse,
  TelemetryRecordResponse,
} from '../types/api'

import { apiBaseUrl } from './baseUrl'

export const API_BASE_URL = apiBaseUrl(import.meta.env.VITE_API_BASE_URL)

export class ApiClientError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.code = code
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  operatorToken?: string,
): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (options.body) headers.set('Content-Type', 'application/json')
  if (operatorToken) headers.set('X-Operator-Token', operatorToken)

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiClientError(
      0,
      'network_error',
      'The local backend could not be reached. Check that FastAPI is running.',
    )
  }

  const responseText = await response.text()
  let body: unknown = null
  if (responseText) {
    try {
      body = JSON.parse(responseText)
    } catch {
      throw new ApiClientError(
        response.status,
        'invalid_response',
        'The backend returned a response the dashboard could not understand.',
      )
    }
  }

  if (!response.ok) {
    const apiError = body as Partial<ApiErrorResponse> | null
    throw new ApiClientError(
      response.status,
      apiError?.error?.code ?? 'request_failed',
      apiError?.error?.message ?? 'The backend request failed.',
    )
  }

  return body as T
}

export function getSystemStatus(signal?: AbortSignal) {
  return request<BackendStatusResponse>('/api/status', { signal })
}

export function getBusArrivals(busStopCode: string, serviceNo: string, signal?: AbortSignal) {
  const query = new URLSearchParams({ bus_stop_code: busStopCode })
  if (serviceNo) query.set('service_no', serviceNo)
  return request<BusArrivalResponse>(`/api/bus-arrivals?${query}`, { signal, cache: 'no-store' })
}

export function getLatestExternalData(signal?: AbortSignal) {
  return request<ExternalSnapshotResponse>('/api/external/latest', { signal })
}

export function refreshExternalData(operatorToken: string, signal?: AbortSignal) {
  return request<ExternalSnapshotResponse>(
    '/api/external/refresh',
    { method: 'POST', signal },
    operatorToken,
  )
}

export function listDevices(operatorToken: string, signal?: AbortSignal) {
  return request<DeviceListResponse>('/api/devices', { signal }, operatorToken)
}

export function getLatestTelemetry(
  operatorToken: string,
  deviceId: string,
  signal?: AbortSignal,
) {
  return request<TelemetryRecordResponse>(
    `/api/devices/${encodeURIComponent(deviceId)}/telemetry/latest`,
    { signal },
    operatorToken,
  )
}

export function getTelemetryHistory(
  operatorToken: string,
  deviceId: string,
  limit = 100,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ limit: String(limit) })
  return request<TelemetryHistoryResponse>(
    `/api/devices/${encodeURIComponent(deviceId)}/telemetry/history?${query.toString()}`,
    { signal },
    operatorToken,
  )
}

export function listCommands(
  operatorToken: string,
  deviceId: string,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ device_id: deviceId, limit: '100' })
  return request<CommandListResponse>(
    `/api/commands?${query.toString()}`,
    { signal },
    operatorToken,
  )
}

export function createCommand(
  operatorToken: string,
  command: CommandCreateRequest,
  signal?: AbortSignal,
) {
  return request<CommandResponse>(
    '/api/commands',
    {
      method: 'POST',
      body: JSON.stringify(command),
      signal,
    },
    operatorToken,
  )
}
