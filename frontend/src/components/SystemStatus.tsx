import type {
  BackendStatusResponse,
  ConnectionState,
  DeviceListResponse,
  BusArrivalResponse,
  ResourceState,
} from '../types/api'
import { deriveJetsonDisplayStatus } from '../utils/dashboardSafety'

interface SystemStatusProps {
  devices: ResourceState<DeviceListResponse>
  external: ResourceState<BusArrivalResponse>
  selectedDeviceId: string
  status: ResourceState<BackendStatusResponse>
}

interface DisplayStatus {
  detail: string
  state: ConnectionState
}

const connectionLabels: Record<ConnectionState, string> = {
  online: 'Online',
  offline: 'Offline',
  degraded: 'Degraded',
  checking: 'Checking',
}

function ServiceCard({ label, service }: { label: string; service: DisplayStatus }) {
  return (
    <article className="status-card">
      <div className="status-card-top">
        <span className="status-label">{label}</span>
        <span className={`status-pill status-pill--${service.state}`}>
          {connectionLabels[service.state]}
        </span>
      </div>
      <p className="status-value">{connectionLabels[service.state]}</p>
      <p className="status-detail">{service.detail}</p>
    </article>
  )
}

export function SystemStatus({
  devices,
  external,
  selectedDeviceId,
  status,
}: SystemStatusProps) {
  const backend: DisplayStatus =
    status.state === 'ready'
      ? { state: 'online', detail: 'FastAPI responded over the local connection' }
      : status.state === 'loading'
        ? { state: 'checking', detail: 'Waiting for the first FastAPI response' }
        : {
            state: 'offline',
            detail: status.errorMessage ?? 'The local backend is unavailable',
          }

  const database: DisplayStatus = status.data
    ? { state: 'online', detail: 'SQLite is initialized and ready' }
    : { state: backend.state, detail: 'Database state requires the backend' }

  const externalApi: DisplayStatus =
    external.state === 'ready'
      ? { state: 'online', detail: 'LTA bus arrivals refresh every 20 seconds' }
      : external.state === 'loading'
        ? { state: 'checking', detail: 'Checking bus arrival estimates with LTA' }
        : external.state === 'empty'
          ? { state: 'degraded', detail: external.data ? 'LTA returned no arrival estimates for this search' : 'Enter a bus stop code to check arrivals' }
          : {
              state: 'offline',
              detail: external.errorMessage ?? 'The last external request failed',
            }

  const jetson = deriveJetsonDisplayStatus(devices, selectedDeviceId)

  return (
    <section className="panel system-panel" aria-labelledby="system-status-title">
      <div className="panel-header">
        <div className="panel-heading">
          <h3 id="system-status-title">System status</h3>
          <p>Heartbeat status is recalculated by FastAPI every two seconds</p>
        </div>
      </div>
      <div className="panel-body status-grid" aria-live="polite">
        <ServiceCard label="Backend" service={backend} />
        <ServiceCard label="SQLite database" service={database} />
        <ServiceCard label="External API" service={externalApi} />
        <ServiceCard label="Jetson Nano" service={jetson} />
      </div>
    </section>
  )
}
