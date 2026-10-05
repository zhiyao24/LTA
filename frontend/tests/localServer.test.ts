import assert from 'node:assert/strict'
import test from 'node:test'
import { localServerOptions } from '../server/localServer.ts'
import { apiBaseUrl } from '../src/api/baseUrl.ts'

test('same-origin URLs work on remote devices without localhost or mixed content', () => {
  for (const input of ['/', '', undefined]) assert.equal(apiBaseUrl(input), '')
  const url = new URL(`${apiBaseUrl('/')}/api/status`, 'https://192.168.88.7:5443')
  assert.equal(url.href, 'https://192.168.88.7:5443/api/status')
  assert.equal(apiBaseUrl('https://example.test/'), 'https://example.test')
  assert.throws(() => apiBaseUrl('https://user:password@example.test'))
  assert.throws(() => apiBaseUrl('javascript:alert(1)'))
})

test('dev proxy targets only loopback; no wildcard CORS or broad filesystem access', () => {
  const server = localServerOptions({}, '/project/frontend')
  assert.equal(server.host, '0.0.0.0')
  assert.equal(server.port, 5173)
  assert.equal(server.https, undefined)
  assert.equal(server.cors, false)
  assert.equal(server.strictPort, true)
  assert.deepEqual(server.fs?.allow, ['/project/frontend'])
  for (const rule of Object.values(server.proxy!)) {
    assert.equal(typeof rule === 'object' && rule.target, 'http://127.0.0.1:8000')
  }
  assert.equal(Object.keys(server.proxy!).some((key) => new RegExp(key.slice(1)).test('/api/status')), true)
})

test('HTTPS fails closed without certificates and validates config', () => {
  assert.throws(() => localServerOptions({ FRONTEND_HTTPS: 'true' }, '/nonexistent/frontend'), /will not fall back/)
  assert.throws(() => localServerOptions({ FRONTEND_HTTPS: 'yes' }, '/project/frontend'))
  for (const port of ['0', '65536', '8000/example', '-1']) {
    assert.throws(() => localServerOptions({ LTA_BACKEND_PORT: port }, '/project/frontend'))
  }
})
