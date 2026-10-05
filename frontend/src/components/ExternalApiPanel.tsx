import type {
  ExternalSnapshotResponse,
  JsonValue,
  ResourceState,
} from '../types/api'

interface ExternalApiPanelProps {
  backendOnline: boolean
  data: ResourceState<ExternalSnapshotResponse>
  isRefreshing: boolean
  onRefresh: () => void
  referenceTime: string | null
  refreshAllowed: boolean
}

const STALE_AFTER_MS = 5 * 60 * 1000

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

function formatValue(value: JsonValue) {
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function LoadingState() {
  return (
    <div className="loading-stack" role="status" aria-label="Loading external API information">
      <div className="loading-line" />
      <div className="loading-line" />
      <div className="loading-line" />
    </div>
  )
}

function MessageState({
  kind,
  title,
  message,
}: {
  kind: 'empty' | 'offline' | 'error'
  title: string
  message: string
}) {
  return (
    <div
      className={`state-message state-message--${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
    >
      <div className="state-message-inner">
        <div className="state-icon" aria-hidden="true">
          {kind === 'empty' ? '—' : '!'}
        </div>
        <h4>{title}</h4>
        <p>{message}</p>
      </div>
    </div>
  )
}

export function ExternalApiPanel({
  backendOnline,
  data,
  isRefreshing,
  onRefresh,
  referenceTime,
  refreshAllowed,
}: ExternalApiPanelProps) {
  const values = data.data ? Object.entries(data.data.data) : []
  const isStale = data.data && referenceTime
    ? new Date(referenceTime).getTime() - new Date(data.data.received_at).getTime() > STALE_AFTER_MS
    : false

  return (
    <section className="panel external-panel" aria-labelledby="external-api-title">
      <div className="panel-header">
        <div className="panel-heading">
          <h3 id="external-api-title">External API information</h3>
          <p>Provider-neutral JSON stored by the local backend</p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing || !backendOnline || !refreshAllowed}
          title={refreshAllowed ? undefined : 'Enter the operator token to refresh'}
        >
          {isRefreshing ? 'Refreshing…' : 'Refresh data'}
        </button>
      </div>
      <div className="panel-body" aria-live="polite">
        {(data.state === 'loading' || isRefreshing) && !data.data && <LoadingState />}
        {data.state === 'empty' && !isRefreshing && (
          <MessageState
            kind="empty"
            title="No information yet"
            message="Select Refresh data to create the first mock snapshot."
          />
        )}
        {data.state === 'offline' && (
          <MessageState
            kind="offline"
            title="Backend is offline"
            message={data.errorMessage ?? 'Start FastAPI and try again.'}
          />
        )}
        {data.state === 'error' && (
          <MessageState
            kind="error"
            title="Could not refresh external data"
            message={data.errorMessage ?? 'The last valid snapshot was kept.'}
          />
        )}
        {data.data && (
          <>
            {(isStale || data.state === 'error') && (
              <div className="warning-banner" role="alert">
                <span className="warning-symbol" aria-hidden="true">!</span>
                <span>
                  <strong>{isStale ? 'Stale snapshot.' : 'Refresh failed.'}</strong>{' '}
                  {isStale
                    ? 'This snapshot is more than five minutes old.'
                    : 'Showing the last valid stored result.'}
                </span>
              </div>
            )}
            <div className="meta-strip">
              <div className="meta-item">
                <span>Source</span>
                <strong>{data.data.source}</strong>
              </div>
              <div className="meta-item">
                <span>Last updated</span>
                <strong>
                  <time dateTime={data.data.received_at}>
                    {formatTime(data.data.received_at)}
                  </time>
                </strong>
              </div>
            </div>
            {values.length === 0 ? (
              <MessageState
                kind="empty"
                title="Snapshot is empty"
                message="The backend stored a valid JSON object with no fields."
              />
            ) : (
              <div className="metric-grid">
                {values.map(([name, value]) => (
                  <article className="metric-card" key={name}>
                    <span className="metric-label">{name}</span>
                    <div className="metric-value metric-value--json">
                      <strong>{formatValue(value)}</strong>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}
