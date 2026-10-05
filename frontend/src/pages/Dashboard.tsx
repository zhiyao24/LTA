import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiClientError,
  createCommand,
  getLatestTelemetry,
  getSystemStatus,
  listDevices,
  listCommands,
} from '../api/client'
import { CommandControls } from '../components/CommandControls'
import { CommandHistory } from '../components/CommandHistory'
import { BusArrivalPanel } from '../components/BusArrivalPanel'
import { Header } from '../components/Header'
import { SystemStatus } from '../components/SystemStatus'
import { TelemetryPanel } from '../components/TelemetryPanel'
import { usePolling } from '../hooks/usePolling'
import { selectedDevice as findSelectedDevice } from '../utils/dashboardSafety'
import { createSubmissionGate } from '../utils/submissionGate'
import type {
  BackendStatusResponse,
  CommandDraft,
  CommandListResponse,
  CommandResponse,
  DeviceListResponse,
  BusArrivalResponse,
  ResourceState,
  TelemetryRecordResponse,
} from '../types/api'

const OPERATOR_TOKEN_KEY = 'lta.operatorToken'
const DEVICE_ID_KEY = 'lta.deviceId'
function initialSessionValue(key: string) {
  return window.sessionStorage.getItem(key) ?? ''
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'An unexpected error occurred.'
}

function errorState(error: unknown): 'offline' | 'error' {
  return error instanceof ApiClientError && error.code === 'network_error'
    ? 'offline'
    : 'error'
}

export function Dashboard() {
  const [systemStatus, setSystemStatus] = useState<ResourceState<BackendStatusResponse>>({
    state: 'loading',
    data: null,
  })
  const [externalData, setExternalData] = useState<ResourceState<BusArrivalResponse>>({
    state: 'empty',
    data: null,
  })
  const [operatorToken, setOperatorToken] = useState(() =>
    initialSessionValue(OPERATOR_TOKEN_KEY),
  )
  const [deviceId, setDeviceId] = useState(() => initialSessionValue(DEVICE_ID_KEY))
  const [devices, setDevices] = useState<ResourceState<DeviceListResponse>>(() => ({
    state: initialSessionValue(OPERATOR_TOKEN_KEY).trim() ? 'loading' : 'empty',
    data: null,
    errorMessage: initialSessionValue(OPERATOR_TOKEN_KEY).trim()
      ? undefined
      : 'Enter the operator token to load device heartbeats.',
  }))
  const [telemetry, setTelemetry] = useState<ResourceState<TelemetryRecordResponse>>(
    () => {
      const hasAccess = Boolean(
        initialSessionValue(OPERATOR_TOKEN_KEY).trim() &&
        initialSessionValue(DEVICE_ID_KEY).trim(),
      )
      return {
        state: hasAccess ? 'loading' : 'empty',
        data: null,
        errorMessage: hasAccess
          ? undefined
          : 'Enter the device ID and operator token to load telemetry.',
      }
    },
  )
  const [commandHistory, setCommandHistory] = useState<ResourceState<CommandListResponse>>(
    () => {
      const hasAccess = Boolean(
        initialSessionValue(OPERATOR_TOKEN_KEY).trim() &&
        initialSessionValue(DEVICE_ID_KEY).trim(),
      )
      return {
        state: hasAccess ? 'loading' : 'empty',
        data: null,
        errorMessage: hasAccess
          ? undefined
          : 'Enter the device ID and operator token to load command history.',
      }
    },
  )
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submissionError, setSubmissionError] = useState<string>()
  const [lastCommand, setLastCommand] = useState<CommandResponse | null>(null)
  const submissionGate = useRef(createSubmissionGate())
  const submissionController = useRef<AbortController | null>(null)

  const pollSystemStatus = useCallback(async (signal: AbortSignal) => {
    try {
      const data = await getSystemStatus(signal)
      setSystemStatus({ state: 'ready', data })
    } catch (error) {
      if (isAbortError(error)) return
      setSystemStatus((current) => ({
        state: errorState(error),
        data: current.data,
        errorMessage: errorMessage(error),
      }))
    }
  }, [])

  const pollCommandHistory = useCallback(
    async (signal: AbortSignal) => {
      if (!operatorToken.trim() || !deviceId.trim()) return
      try {
        const data = await listCommands(
          operatorToken.trim(),
          deviceId.trim(),
          signal,
        )
        setCommandHistory({
          state: data.count === 0 ? 'empty' : 'ready',
          data,
        })
        setLastCommand(data.items[0] ?? null)
      } catch (error) {
        if (isAbortError(error)) return
        setCommandHistory((current) => ({
          state: errorState(error),
          data: current.data,
          errorMessage: errorMessage(error),
        }))
      }
    },
    [deviceId, operatorToken],
  )

  const pollDevices = useCallback(
    async (signal: AbortSignal) => {
      if (!operatorToken.trim()) return
      try {
        const data = await listDevices(operatorToken.trim(), signal)
        setDevices({ state: data.count === 0 ? 'empty' : 'ready', data })
      } catch (error) {
        if (isAbortError(error)) return
        setDevices((current) => ({
          state: errorState(error),
          data: current.data,
          errorMessage: errorMessage(error),
        }))
      }
    },
    [operatorToken],
  )

  const pollTelemetry = useCallback(
    async (signal: AbortSignal) => {
      if (!operatorToken.trim() || !deviceId.trim()) return
      try {
        const data = await getLatestTelemetry(
          operatorToken.trim(),
          deviceId.trim(),
          signal,
        )
        setTelemetry({ state: 'ready', data })
      } catch (error) {
        if (isAbortError(error)) return
        if (
          error instanceof ApiClientError &&
          (error.code === 'telemetry_not_found' || error.code === 'device_not_found')
        ) {
          setTelemetry({ state: 'empty', data: null, errorMessage: error.message })
          return
        }
        setTelemetry((current) => ({
          state: errorState(error),
          data: current.data,
          errorMessage: errorMessage(error),
        }))
      }
    },
    [deviceId, operatorToken],
  )

  usePolling(pollSystemStatus, { intervalMs: 5_000 })
  usePolling(pollDevices, {
    enabled: Boolean(operatorToken.trim()),
    intervalMs: 2_000,
  })
  usePolling(pollTelemetry, {
    enabled: Boolean(operatorToken.trim() && deviceId.trim()),
    intervalMs: 2_000,
  })
  usePolling(pollCommandHistory, {
    enabled: Boolean(operatorToken.trim() && deviceId.trim()),
    intervalMs: 3_000,
  })

  useEffect(
    () => () => {
      submissionController.current?.abort()
    },
    [],
  )

  function handleOperatorTokenChange(value: string) {
    setOperatorToken(value)
    setSubmissionError(undefined)
    if (value) window.sessionStorage.setItem(OPERATOR_TOKEN_KEY, value)
    else window.sessionStorage.removeItem(OPERATOR_TOKEN_KEY)
    if (value.trim()) {
      setDevices((current) => ({ state: 'loading', data: current.data }))
    } else {
      setDevices({
        state: 'empty',
        data: null,
        errorMessage: 'Enter the operator token to load device heartbeats.',
      })
    }
    if (value.trim() && deviceId.trim()) {
      setCommandHistory((current) => ({ state: 'loading', data: current.data }))
      setTelemetry({ state: 'loading', data: null })
    } else {
      setCommandHistory({
        state: 'empty',
        data: null,
        errorMessage: 'Enter the device ID and operator token to load command history.',
      })
      setTelemetry({
        state: 'empty',
        data: null,
        errorMessage: 'Enter the device ID and operator token to load telemetry.',
      })
      setLastCommand(null)
    }
  }

  function handleDeviceIdChange(value: string) {
    setDeviceId(value)
    setSubmissionError(undefined)
    if (value) window.sessionStorage.setItem(DEVICE_ID_KEY, value)
    else window.sessionStorage.removeItem(DEVICE_ID_KEY)
    if (value.trim() && operatorToken.trim()) {
      setCommandHistory((current) => ({ state: 'loading', data: current.data }))
      setTelemetry({ state: 'loading', data: null })
    } else {
      setCommandHistory({
        state: 'empty',
        data: null,
        errorMessage: 'Enter the device ID and operator token to load command history.',
      })
      setTelemetry({
        state: 'empty',
        data: null,
        errorMessage: 'Enter the device ID and operator token to load telemetry.',
      })
      setLastCommand(null)
    }
  }

  async function handleCommandSubmit(draft: CommandDraft) {
    return submissionGate.current.run(async () => {
      const controller = new AbortController()
      submissionController.current = controller
      setIsSubmitting(true)
      setSubmissionError(undefined)
      try {
        const command = await createCommand(operatorToken.trim(), {
          request_id: crypto.randomUUID(),
          device_id: deviceId.trim(),
          command_type: draft.commandType,
          payload: draft.payload,
          expires_in_seconds: 30,
        }, controller.signal)
        setLastCommand(command)
        setCommandHistory((current) => {
          const previous = current.data?.items ?? []
          const items = [command, ...previous.filter((item) => item.id !== command.id)]
          return { state: 'ready', data: { items, count: items.length } }
        })
        return true
      } catch (error) {
        if (!isAbortError(error)) setSubmissionError(errorMessage(error))
        return false
      } finally {
        if (submissionController.current === controller) {
          submissionController.current = null
        }
        setIsSubmitting(false)
      }
    })
  }

  const backendOnline = systemStatus.state === 'ready'
  const selectedDevice = findSelectedDevice(devices, deviceId)
  let controlsDisabled = false
  let disabledReason = ''
  if (!backendOnline) {
    controlsDisabled = true
    disabledReason = 'Start the local FastAPI backend before queueing commands.'
  } else if (!deviceId.trim()) {
    controlsDisabled = true
    disabledReason = 'Enter the registered simulator device ID.'
  } else if (!operatorToken.trim()) {
    controlsDisabled = true
    disabledReason = 'Enter the backend operator token for this browser session.'
  } else if (
    devices.state !== 'ready' ||
    !selectedDevice ||
    selectedDevice.status !== 'online'
  ) {
    controlsDisabled = true
    disabledReason = 'Start the simulator and wait for an online heartbeat before queueing commands.'
  }

  return (
    <>
      <a className="skip-link" href="#dashboard-content">Skip to dashboard</a>
      <Header backendState={systemStatus.state} />
      <main className="dashboard-main" id="dashboard-content">
        <div className="page-intro">
          <div>
            <h2>Operations overview</h2>
            <p>
              This page polls FastAPI and SQLite locally. Commands remain simulation-only and expire after 30 seconds.
            </p>
          </div>
          <span className="local-only-note">Laptop backend only</span>
        </div>

        <div className="dashboard-grid">
          <SystemStatus
            devices={devices}
            status={systemStatus}
            external={externalData}
            selectedDeviceId={deviceId}
          />
          <BusArrivalPanel
            data={externalData}
            onDataChange={setExternalData}
          />
          <TelemetryPanel device={selectedDevice} telemetry={telemetry} />
          <CommandControls
            deviceId={deviceId}
            disabled={controlsDisabled}
            disabledReason={disabledReason}
            isSubmitting={isSubmitting}
            lastCommand={lastCommand}
            onDeviceIdChange={handleDeviceIdChange}
            onOperatorTokenChange={handleOperatorTokenChange}
            onSubmit={handleCommandSubmit}
            operatorToken={operatorToken}
            submissionError={submissionError}
          />
          <CommandHistory history={commandHistory} />
        </div>

        <p className="mock-footer">
          Heartbeats and telemetry come from the dry-run simulator. App data comes from FastAPI; the optional map connects to Google. The browser never connects directly to the Jetson.
        </p>
      </main>
    </>
  )
}
