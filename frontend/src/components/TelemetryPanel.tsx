import type {
  DeviceResponse,
  ResourceState,
  TelemetryRecordResponse,
} from '../types/api'
import {
  telemetrySafetyState,
  visibleTelemetryMetrics,
} from '../utils/dashboardSafety'

interface TelemetryPanelProps {
  device: DeviceResponse | null
  telemetry: ResourceState<TelemetryRecordResponse>
}

function formatTime(timestamp?: string | null) {
  if (!timestamp) return 'Not provided'
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

export function TelemetryPanel({ device, telemetry }: TelemetryPanelProps) {
  const sample = telemetry.data
  const readings = visibleTelemetryMetrics(sample?.data)
  const { deviceOffline } = telemetrySafetyState(device, telemetry)
  const showReadings = Boolean(sample && readings.length > 0)

  let emptyTitle = 'No telemetry yet'
  let emptyMessage = 'Start the simulator to send the first validated reading.'
  if (!device) {
    emptyTitle = 'Device not connected'
    emptyMessage = 'Enter a device ID and start its simulator to receive telemetry.'
  } else if (deviceOffline) {
    emptyTitle = 'Jetson is offline'
    emptyMessage = 'No stored telemetry is available for the disconnected device.'
  }

  return (
    <section className="panel telemetry-panel" aria-labelledby="telemetry-title">
      <div className="panel-header">
        <div className="panel-heading">
          <h3 id="telemetry-title">Jetson telemetry</h3>
          <p>Validated simulated readings received by FastAPI</p>
        </div>
      </div>
      <div className="panel-body" aria-live="polite">
        {deviceOffline && sample && (
          <div className="warning-banner" role="alert">
            <span className="warning-symbol" aria-hidden="true">!</span>
            <span><strong>Jetson offline.</strong> Showing the last stored readings only.</span>
          </div>
        )}

        {sample?.is_stale && (
          <div className="warning-banner" role="alert">
            <span className="warning-symbol" aria-hidden="true">!</span>
            <span>
              <strong>Stale telemetry.</strong> No new reading has arrived within{' '}
              {sample.stale_after_seconds} seconds.
            </span>
          </div>
        )}

        {(telemetry.state === 'error' || telemetry.state === 'offline') && (
          <div className="inline-error" role="alert">
            <strong>Telemetry unavailable.</strong>{' '}
            {telemetry.errorMessage ?? 'The latest reading could not be loaded.'}
          </div>
        )}

        {telemetry.state === 'loading' && !sample && (
          <div className="loading-stack" role="status" aria-label="Loading Jetson telemetry">
            <div className="loading-line" />
            <div className="loading-line" />
            <div className="loading-line" />
          </div>
        )}

        {!showReadings && telemetry.state !== 'loading' && (
          <div className="state-message" role="status">
            <div className="state-message-inner">
              <div className="state-icon" aria-hidden="true">—</div>
              <h4>{emptyTitle}</h4>
              <p>{telemetry.errorMessage ?? emptyMessage}</p>
            </div>
          </div>
        )}

        {showReadings && sample && (
          <>
            <div className="metric-grid">
              {readings.map((reading) => (
                <article className="metric-card" key={String(reading.key)}>
                  <span className="metric-label">{reading.label}</span>
                  <div className="metric-value">
                    <strong>{reading.value}</strong>
                    <span>{reading.unit}</span>
                  </div>
                </article>
              ))}
            </div>
            <div className="telemetry-times">
              <p className="telemetry-footer">
                Backend received: <time dateTime={sample.received_at}>{formatTime(sample.received_at)}</time>
              </p>
              <p className="telemetry-footer">
                Device time: <time dateTime={sample.device_timestamp}>{formatTime(sample.device_timestamp)}</time>
              </p>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
