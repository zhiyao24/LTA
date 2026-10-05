import { useEffect, useRef } from 'react'

interface PollingOptions {
  enabled?: boolean
  intervalMs: number
  pauseWhenHidden?: boolean
  restartKey?: string
}

export function usePolling(
  poll: (signal: AbortSignal) => Promise<void>,
  {
    enabled = true,
    intervalMs,
    pauseWhenHidden = true,
    restartKey = '',
  }: PollingOptions,
) {
  const pollRef = useRef(poll)

  useEffect(() => {
    pollRef.current = poll
  }, [poll])

  useEffect(() => {
    if (!enabled) return

    let stopped = false
    let timer: number | undefined
    let controller: AbortController | undefined
    let generation = 0

    const clearCurrentWork = () => {
      generation += 1
      if (timer !== undefined) window.clearTimeout(timer)
      controller?.abort()
      timer = undefined
      controller = undefined
    }

    const schedule = () => {
      if (stopped || (pauseWhenHidden && document.hidden)) return
      timer = window.setTimeout(run, intervalMs)
    }

    const run = async () => {
      if (stopped || (pauseWhenHidden && document.hidden)) return
      const runGeneration = generation
      const runController = new AbortController()
      controller = runController
      try {
        await pollRef.current(runController.signal)
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          // The polling callback owns its user-facing error state.
          console.error('Polling callback failed safely')
        }
      } finally {
        // Ignore cleanup from a request invalidated by a visibility change.
        if (runGeneration === generation) {
          if (controller === runController) controller = undefined
          schedule()
        }
      }
    }

    const handleVisibilityChange = () => {
      clearCurrentWork()
      if (!document.hidden) void run()
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    void run()

    return () => {
      stopped = true
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      clearCurrentWork()
    }
  }, [enabled, intervalMs, pauseWhenHidden, restartKey])
}
