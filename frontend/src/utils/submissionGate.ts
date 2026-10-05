export interface SubmissionGate {
  run: (operation: () => Promise<boolean>) => Promise<boolean>
}

/** Allow at most one command submission until the active request settles. */
export function createSubmissionGate(): SubmissionGate {
  let active = false

  return {
    async run(operation) {
      if (active) return false
      active = true
      try {
        return await operation()
      } finally {
        active = false
      }
    },
  }
}
