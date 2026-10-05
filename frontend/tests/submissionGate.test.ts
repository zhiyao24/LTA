import assert from 'node:assert/strict'
import test from 'node:test'

import { createSubmissionGate } from '../src/utils/submissionGate.ts'


test('rapid duplicate button submissions start only one request', async () => {
  const gate = createSubmissionGate()
  let releaseFirst: ((value: boolean) => void) | undefined
  let calls = 0

  const first = gate.run(
    () => new Promise<boolean>((resolve) => {
      calls += 1
      releaseFirst = resolve
    }),
  )
  const duplicate = await gate.run(async () => {
    calls += 1
    return true
  })

  assert.equal(duplicate, false)
  assert.equal(calls, 1)

  releaseFirst?.(true)
  assert.equal(await first, true)

  const later = await gate.run(async () => {
    calls += 1
    return true
  })
  assert.equal(later, true)
  assert.equal(calls, 2)
})

test('the gate reopens after a failed request', async () => {
  const gate = createSubmissionGate()

  await assert.rejects(
    gate.run(async () => {
      throw new Error('simulated request failure')
    }),
    /simulated request failure/,
  )

  assert.equal(await gate.run(async () => true), true)
})
