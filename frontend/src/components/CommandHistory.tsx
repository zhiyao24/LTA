import type {
  CommandResponse,
  CommandStatus,
  CommandListResponse,
  ResourceState,
} from '../types/api'

interface CommandHistoryProps {
  history: ResourceState<CommandListResponse>
}

const statusLabels: Record<CommandStatus, string> = {
  pending: 'Pending',
  delivered: 'Delivered',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  expired: 'Expired',
  cancelled: 'Cancelled',
}

function formatTime(timestamp: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp))
}

function summarize(command: CommandResponse) {
  switch (command.command_type) {
    case 'STOP':
      return 'Simulated safe-state request'
    case 'SET_MODE':
      return `Mode: ${String(command.payload.mode)}`
    case 'SET_SPEED':
      return `Speed: ${String(command.payload.speed_percent)}%`
    case 'SEND_MESSAGE':
      return `Message: ${String(command.payload.message)}`
  }
}

function resultText(command: CommandResponse) {
  if (command.result) return JSON.stringify(command.result)
  if (command.status === 'pending') return 'Waiting for simulator retrieval'
  if (command.status === 'delivered') return 'Delivered; waiting for acknowledgement'
  if (command.status === 'running') return 'Simulator reports running'
  if (command.status === 'expired') return 'Expired before completion'
  return 'No result was provided'
}

export function CommandHistory({ history }: CommandHistoryProps) {
  const commands = history.data?.items ?? []

  return (
    <section className="panel history-panel" aria-labelledby="command-history-title">
      <div className="panel-header">
        <div className="panel-heading">
          <h3 id="command-history-title">Command history</h3>
          <p>Polled from SQLite every three seconds while this tab is visible</p>
        </div>
      </div>
      <div className="panel-body" aria-live="polite">
        {history.state === 'loading' && commands.length === 0 && (
          <div className="loading-stack" role="status" aria-label="Loading command history">
            <div className="loading-line" />
            <div className="loading-line" />
            <div className="loading-line" />
          </div>
        )}

        {history.state === 'empty' && commands.length === 0 && (
          <div className="state-message" role="status">
            <div className="state-message-inner">
              <div className="state-icon" aria-hidden="true">—</div>
              <h4>No commands to display</h4>
              <p>{history.errorMessage ?? 'Queue a validated simulation command to begin.'}</p>
            </div>
          </div>
        )}

        {(history.state === 'error' || history.state === 'offline') && (
          <div
            className={`inline-error ${history.state === 'offline' ? 'inline-error--offline' : ''}`}
            role="alert"
          >
            <strong>History unavailable.</strong>{' '}
            {history.errorMessage ?? 'The command list could not be loaded.'}
          </div>
        )}

        {commands.length > 0 && (
          <div className="history-wrap">
            <table className="history-table">
              <thead>
                <tr>
                  <th scope="col">Command</th>
                  <th scope="col">ID</th>
                  <th scope="col">Time</th>
                  <th scope="col">Status</th>
                  <th scope="col">Result or error</th>
                </tr>
              </thead>
              <tbody>
                {commands.map((command) => (
                  <tr key={command.id}>
                    <td data-label="Command">
                      <span className="history-command">{command.command_type}</span>
                      <span className="history-summary">{summarize(command)}</span>
                    </td>
                    <td data-label="ID">
                      <code className="command-id">{command.id}</code>
                    </td>
                    <td data-label="Time">
                      <time dateTime={command.created_at}>{formatTime(command.created_at)}</time>
                    </td>
                    <td data-label="Status">
                      <span className={`status-pill status-pill--${command.status}`}>
                        {statusLabels[command.status]}
                      </span>
                    </td>
                    <td className="history-result" data-label="Result or error">
                      {resultText(command)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
