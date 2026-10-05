# Project instructions

## Project paths

- `frontend/`: React, Vite, and TypeScript dashboard. App data goes through FastAPI; the optional, user-enabled Google map loads directly from Google with a browser-visible restricted Maps key. LTA and device credentials must never be sent to the browser.
- `backend/`: FastAPI API, command policy, external-API adapter, and SQLite owner.
- `jetson-agent/`: Python Wi-Fi polling agent and simulator. It is simulation-only.
- `backend/data/`: local SQLite data. Database files must stay uncommitted.
- `tests/`: repository-wide safety and simulated end-to-end tests.
- `scripts/`: local development and verification helpers.
- `.local-https/`: ignored local CA/server certificates and private keys. Never serve, commit or share private keys; never change a device trust store automatically. Only the public CA certificate may be shared for owner-approved trust setup.
- `docs/`: architecture and hardware-safety documentation.
- `.venv/`: existing local Python environment; reuse it and never commit it.

## Development commands

Run the backend from the project root:

```sh
.venv/bin/python -m uvicorn backend.app.main:app --reload --port 8000
```

Run the frontend in another terminal:

```sh
npm --prefix frontend run dev
```

Run all automated checks:

```sh
./scripts/check-all.sh
```

The individual checks are:

```sh
.venv/bin/python -m pytest
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Safety rules

- Keep the project local; do not add deployment or cloud configuration.
- Preserve unrelated work and inspect existing files before editing them.
- Real hardware control must remain unavailable and `DRY_RUN` must default to `true`.
- Never add arbitrary shell/terminal input, `eval`, `exec`, `os.system`, or subprocess execution to a command path.
- Commands must be explicitly allowlisted, schema-validated, range-bounded, expiring, authenticated, duplicate-resistant, and audited.
- Operator and Jetson credentials are separate roles and must use different values.
- Never commit or log passwords, API keys, device tokens, populated `.env` files, or local databases.
- The frontend is not a safety boundary. FastAPI and the Jetson agent must independently reject unsafe input.
- Network loss, invalid input, handler failure, or uncertain command state must return simulated outputs to safe/off state.
- Software STOP is only a supervisory request. Never describe it as a substitute for a physical, hard-wired emergency stop or power disconnect.
- Wi-Fi is for supervisory commands and telemetry, never a real-time motor-control loop. Time-critical control and interlocks must remain local to suitable hardware.
- Keep Wi-Fi as the active default transport. BLE must remain mock-only until the exact Jetson adapter, BlueZ version, GATT manager, and advertising manager are verified.
- Never add browser Web Bluetooth. A future BLE path must remain browser → FastAPI → Bleak client → Jetson GATT service.
- BLE pairing does not replace the separate operator and device authentication boundaries or application-level message authentication.
- Do not enable GPIO, PWM, serial, motors, or other actuators without explicit user approval and completion of `docs/hardware-safety.md`.

## Definition of done

A change is complete only when it:

1. Preserves the safety defaults and credential boundaries above.
2. Includes tests for normal, invalid, unauthorized, duplicate, expired, and communication-loss behavior where applicable.
3. Passes Python tests plus frontend tests, lint, type checking, and production build.
4. Uses simulation for integration testing and does not activate real hardware.
5. Updates beginner-facing documentation when setup, behavior, or safety assumptions change.
