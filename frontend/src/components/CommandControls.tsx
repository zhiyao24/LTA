import { useEffect, useRef, useState } from 'react'
import type { CommandDraft, CommandResponse, OperatingMode } from '../types/api'

interface CommandControlsProps {
  deviceId: string
  disabled: boolean
  disabledReason: string
  isSubmitting: boolean
  lastCommand: CommandResponse | null
  onDeviceIdChange: (value: string) => void
  onOperatorTokenChange: (value: string) => void
  onSubmit: (command: CommandDraft) => Promise<boolean>
  operatorToken: string
  submissionError?: string
}

const operatingModes: Array<{ label: string; value: OperatingMode }> = [
  { value: 'standby', label: 'Standby' },
  { value: 'manual', label: 'Manual control' },
  { value: 'assisted', label: 'Assisted operation' },
]

function describeCommand(command: CommandDraft) {
  switch (command.commandType) {
    case 'STOP':
      return 'STOP — request the simulated safe state'
    case 'SET_MODE':
      return `SET_MODE — ${command.payload.mode}`
    case 'SET_SPEED':
      return `SET_SPEED — ${command.payload.speed_percent}%`
    case 'SEND_MESSAGE':
      return `SEND_MESSAGE — ${command.payload.message}`
  }
}

export function CommandControls({
  deviceId,
  disabled,
  disabledReason,
  isSubmitting,
  lastCommand,
  onDeviceIdChange,
  onOperatorTokenChange,
  onSubmit,
  operatorToken,
  submissionError,
}: CommandControlsProps) {
  const [mode, setMode] = useState<OperatingMode>('standby')
  const [speedPercent, setSpeedPercent] = useState(0)
  const [message, setMessage] = useState('')
  const [pendingCommand, setPendingCommand] = useState<CommandDraft | null>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const confirmingRef = useRef(false)
  const controlsDisabled = disabled || isSubmitting

  useEffect(() => {
    const dialog = dialogRef.current
    if (pendingCommand && dialog && !dialog.open) dialog.showModal()
  }, [pendingCommand])

  function requestCommand(command: CommandDraft) {
    if (controlsDisabled) return
    setPendingCommand(command)
  }

  function cancelConfirmation() {
    if (isSubmitting) return
    dialogRef.current?.close()
    setPendingCommand(null)
  }

  async function confirmCommand() {
    if (!pendingCommand || confirmingRef.current || controlsDisabled) return
    confirmingRef.current = true
    try {
      const submitted = await onSubmit(pendingCommand)
      if (submitted && pendingCommand.commandType === 'SEND_MESSAGE') setMessage('')
      dialogRef.current?.close()
      setPendingCommand(null)
    } finally {
      confirmingRef.current = false
    }
  }

  return (
    <section className="panel command-panel" aria-labelledby="command-controls-title">
      <div className="panel-header">
        <div className="panel-heading">
          <h3 id="command-controls-title">Command controls</h3>
          <p>Authenticated, expiring simulation commands only</p>
        </div>
      </div>
      <div className="panel-body">
        <div className="access-grid">
          <div className="field-group">
            <label className="field-label" htmlFor="device-id">Device ID</label>
            <input
              className="text-input"
              id="device-id"
              value={deviceId}
              onChange={(event) => onDeviceIdChange(event.target.value)}
              placeholder="jetson-simulator"
              autoComplete="off"
              disabled={isSubmitting}
            />
          </div>
          <div className="field-group">
            <label className="field-label" htmlFor="operator-token">Operator token</label>
            <input
              className="text-input"
              id="operator-token"
              type="password"
              value={operatorToken}
              onChange={(event) => onOperatorTokenChange(event.target.value)}
              placeholder="Enter backend operator token"
              autoComplete="off"
              spellCheck={false}
              disabled={isSubmitting}
            />
          </div>
        </div>
        <p className="field-help access-help">
          The operator token stays in this browser tab only. The Jetson token is never sent to the browser.
        </p>

        {disabled && (
          <div className="control-lockout" id="control-availability" role="status">
            <span className="warning-symbol" aria-hidden="true">!</span>
            <span><strong>Controls locked.</strong> {disabledReason}</span>
          </div>
        )}

        {submissionError && (
          <div className="inline-error" role="alert">
            <strong>Command not queued.</strong> {submissionError}
          </div>
        )}

        {lastCommand && (
          <div className="submission-result" role="status">
            <span>Latest command</span>
            <code>{lastCommand.id}</code>
            <strong>{lastCommand.status}</strong>
          </div>
        )}

        <div className="stop-zone">
          <button
            className="stop-button"
            type="button"
            onClick={() => requestCommand({ commandType: 'STOP', payload: {} })}
            disabled={controlsDisabled}
            aria-describedby={disabled ? 'control-availability' : 'stop-help'}
          >
            <span className="stop-symbol" aria-hidden="true" />
            {isSubmitting ? 'SUBMITTING…' : 'STOP'}
          </button>
          <p className="stop-help" id="stop-help">
            Highest-priority simulation request. It is not a replacement for a physical emergency stop.
          </p>
        </div>

        <div className="control-divider" />

        <div className="control-form">
          <div className="command-row">
            <div className="field-group">
              <label className="field-label" htmlFor="operating-mode">Operating mode</label>
              <select
                className="select-input"
                id="operating-mode"
                value={mode}
                onChange={(event) => setMode(event.target.value as OperatingMode)}
                disabled={controlsDisabled}
              >
                {operatingModes.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <button
              className="secondary-button action-button"
              type="button"
              disabled={controlsDisabled}
              onClick={() => requestCommand({ commandType: 'SET_MODE', payload: { mode } })}
            >
              Queue mode
            </button>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="speed-range">Speed target</label>
            <div className="speed-row">
              <input
                className="range-input"
                id="speed-range"
                type="range"
                min="0"
                max="100"
                step="1"
                value={speedPercent}
                onChange={(event) => setSpeedPercent(Number(event.target.value))}
                disabled={controlsDisabled}
                aria-describedby="speed-help"
              />
              <input
                className="number-input"
                aria-label="Speed target percentage"
                type="number"
                min="0"
                max="100"
                step="1"
                value={speedPercent}
                onChange={(event) =>
                  setSpeedPercent(Math.min(100, Math.max(0, Number(event.target.value))))
                }
                disabled={controlsDisabled}
              />
            </div>
            <p className="field-help" id="speed-help">
              Simulated percentage from 0 to 100. Hardware outputs remain off.
            </p>
            <button
              className="secondary-button action-button"
              type="button"
              disabled={controlsDisabled}
              onClick={() =>
                requestCommand({
                  commandType: 'SET_SPEED',
                  payload: { speed_percent: speedPercent },
                })
              }
            >
              Queue speed
            </button>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="operator-message">Message</label>
            <textarea
              className="text-area"
              id="operator-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              maxLength={500}
              rows={3}
              disabled={controlsDisabled}
              placeholder="Plain text for the simulator"
            />
            <p className="field-help">Plain text only; it is never executed as a command.</p>
            <button
              className="secondary-button action-button"
              type="button"
              disabled={controlsDisabled || message.length === 0}
              onClick={() =>
                requestCommand({ commandType: 'SEND_MESSAGE', payload: { message } })
              }
            >
              Send message
            </button>
          </div>
        </div>

        {pendingCommand && (
          <dialog
            className="confirmation-dialog"
            ref={dialogRef}
            aria-labelledby="confirm-command-title"
            onCancel={(event) => {
              event.preventDefault()
              cancelConfirmation()
            }}
          >
            <div className="dialog-content">
              <p className="dialog-kicker">Confirmation required</p>
              <h4 id="confirm-command-title">Queue this simulation command?</h4>
              <p><strong>{describeCommand(pendingCommand)}</strong></p>
              <p>The command expires after 30 seconds and is sent only to FastAPI.</p>
              <div className="dialog-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={cancelConfirmation}
                  disabled={isSubmitting}
                  autoFocus
                >
                  Cancel
                </button>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => void confirmCommand()}
                  disabled={controlsDisabled}
                >
                  {isSubmitting ? 'Submitting…' : 'Confirm command'}
                </button>
              </div>
            </div>
          </dialog>
        )}
      </div>
    </section>
  )
}
