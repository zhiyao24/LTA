import type {
  DashboardResponse,
  MockScenario,
  OperatingMode,
} from '../types/api'

export interface MockScenarioOption {
  value: MockScenario
  label: string
}

export const mockScenarioOptions: MockScenarioOption[] = [
  { value: 'ready', label: 'Live example' },
  { value: 'loading', label: 'Loading example' },
  { value: 'offline', label: 'Jetson offline' },
  { value: 'stale', label: 'Stale telemetry' },
  { value: 'empty', label: 'Empty example' },
  { value: 'error', label: 'API error' },
]

export const operatingModes: Array<{
  value: OperatingMode
  label: string
}> = [
  { value: 'standby', label: 'Standby' },
  { value: 'manual', label: 'Manual control' },
  { value: 'assisted', label: 'Assisted operation' },
]

const minutesAgo = (minutes: number) =>
  new Date(Date.now() - minutes * 60_000).toISOString()

const createReadyDashboard = (): DashboardResponse => ({
  system: {
    backend: {
      state: 'online',
      detail: 'Local service responding normally',
    },
    externalApi: {
      state: 'online',
      detail: 'Latest request completed',
    },
    jetson: {
      state: 'online',
      detail: 'Connected over local Wi-Fi',
    },
    lastHeartbeat: minutesAgo(1),
  },
  externalApi: {
    state: 'ready',
    source: 'Local weather gateway',
    lastUpdated: minutesAgo(2),
    values: [
      { id: 'air-temperature', label: 'Air temperature', value: '27.8', unit: '°C' },
      { id: 'humidity', label: 'Relative humidity', value: '71', unit: '%' },
      { id: 'wind-speed', label: 'Wind speed', value: '12.4', unit: 'km/h' },
      { id: 'visibility', label: 'Visibility', value: '9.6', unit: 'km' },
    ],
  },
  telemetry: {
    state: 'ready',
    lastReceived: minutesAgo(1),
    isStale: false,
    staleAfterSeconds: 120,
    readings: [
      { id: 'cpu-temperature', label: 'CPU temperature', value: '46.8', unit: '°C' },
      { id: 'memory-use', label: 'Memory use', value: '38', unit: '%' },
      { id: 'supply-voltage', label: 'Supply voltage', value: '5.02', unit: 'V' },
      { id: 'wifi-signal', label: 'Wi-Fi signal', value: '-56', unit: 'dBm' },
    ],
  },
  commandHistory: {
    state: 'ready',
    commands: [
      {
        id: 'mock-command-3',
        commandType: 'SET_MODE',
        summary: 'Standby · 0% speed',
        createdAt: minutesAgo(3),
        status: 'completed',
        result: 'Mock acknowledgement received',
      },
      {
        id: 'mock-command-2',
        commandType: 'SET_SPEED',
        summary: 'Manual control · 24% speed',
        createdAt: minutesAgo(18),
        status: 'delivered',
        result: 'Accepted by the mock Jetson',
      },
      {
        id: 'mock-command-1',
        commandType: 'STOP',
        summary: 'Immediate stop request',
        createdAt: minutesAgo(46),
        status: 'completed',
        result: 'Mock outputs returned to safe state',
      },
    ],
  },
})

export function createMockDashboard(scenario: MockScenario): DashboardResponse {
  const dashboard = createReadyDashboard()

  if (scenario === 'loading') {
    return {
      ...dashboard,
      system: {
        backend: { state: 'checking', detail: 'Checking local service' },
        externalApi: { state: 'checking', detail: 'Waiting for first response' },
        jetson: { state: 'checking', detail: 'Looking for a heartbeat' },
        lastHeartbeat: null,
      },
      externalApi: { ...dashboard.externalApi, state: 'loading', values: [] },
      telemetry: { ...dashboard.telemetry, state: 'loading', readings: [] },
      commandHistory: { state: 'loading', commands: [] },
    }
  }

  if (scenario === 'offline') {
    return {
      ...dashboard,
      system: {
        ...dashboard.system,
        jetson: { state: 'offline', detail: 'No heartbeat within 2 minutes' },
        lastHeartbeat: minutesAgo(18),
      },
      telemetry: {
        ...dashboard.telemetry,
        state: 'offline',
        isStale: true,
        lastReceived: minutesAgo(18),
        readings: [],
      },
    }
  }

  if (scenario === 'stale') {
    return {
      ...dashboard,
      system: {
        ...dashboard.system,
        jetson: { state: 'degraded', detail: 'Connected, but data is delayed' },
        lastHeartbeat: minutesAgo(7),
      },
      telemetry: {
        ...dashboard.telemetry,
        isStale: true,
        lastReceived: minutesAgo(7),
      },
    }
  }

  if (scenario === 'empty') {
    return {
      ...dashboard,
      externalApi: {
        ...dashboard.externalApi,
        state: 'empty',
        lastUpdated: null,
        values: [],
      },
      telemetry: {
        ...dashboard.telemetry,
        state: 'empty',
        lastReceived: null,
        readings: [],
      },
      commandHistory: { state: 'empty', commands: [] },
    }
  }

  if (scenario === 'error') {
    return {
      ...dashboard,
      system: {
        ...dashboard.system,
        externalApi: { state: 'offline', detail: 'Last request failed' },
      },
      externalApi: {
        ...dashboard.externalApi,
        state: 'error',
        lastUpdated: minutesAgo(12),
        values: [],
        errorMessage: 'The mock source returned an invalid response.',
      },
      commandHistory: {
        state: 'error',
        commands: [],
        errorMessage: 'Command history could not be loaded.',
      },
    }
  }

  return dashboard
}
