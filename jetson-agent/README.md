# Jetson Nano simulation agent

This directory contains an offline simulator and a lightweight HTTP polling
agent. Both paths are **simulation only**. They never access GPIO, PWM, serial
devices, system services, or a shell.

Wi-Fi/HTTP remains the active transport. `transports/bluetooth.py` is an
in-memory GATT protocol mock only; it does not use BlueZ, advertise, or access a
Bluetooth adapter. The UUID and framing contract is documented in
`../docs/bluetooth.md`.

The runtime code targets Python 3.6 or newer and has no third-party dependency.
It does not require root access.

## Safety defaults

- `DRY_RUN` defaults to `true`.
- `DRY_RUN=false` is deliberately rejected because real hardware handlers do
  not exist yet.
- Every simulated output begins off: stopped, standby mode, 0% speed, and
  `outputs_enabled=false`.
- Communication loss, invalid commands, duplicates, and handler failures return
  the simulation state to those safe defaults.
- Only `STOP`, `SET_MODE`, `SET_SPEED`, and `SEND_MESSAGE` have handlers.
- Message text remains inert data and is never run as a command.
- Software STOP is a supervisory request, not a substitute for a physical,
  hard-wired emergency stop or power disconnect.
- Wi-Fi is used for commands and telemetry only. It must never provide a
  real-time motor-control loop; deterministic control and interlocks must stay
  local to suitable hardware.

## Configuration

Set these variables in the Jetson process environment:

| Variable | Purpose |
| --- | --- |
| `BACKEND_URL` | Laptop backend URL reachable over local Wi-Fi |
| `DEVICE_ID` | Device ID registered in the backend database |
| `DEVICE_TOKEN` | Jetson-only token matching backend `JETSON_API_TOKEN` |
| `POLL_INTERVAL_SECONDS` | Delay between polls; defaults to 2 seconds |
| `REQUEST_TIMEOUT_SECONDS` | Per-request timeout; defaults to 5 seconds |
| `DRY_RUN` | Must remain `true` for this implementation |

Do not commit a populated `.env` file. The agent reads process environment
variables directly, so you can load a private file from the project root with:

```sh
set -a
source jetson-agent/.env
set +a
```

`BACKEND_URL=http://localhost:8000` works only when the simulator and backend
run on the same computer. On a Jetson, set it to the laptop's current local
Wi-Fi address; do not hardcode that address in source code.

## Offline simulator first

This exercises one heartbeat, one telemetry sample, command validation,
acknowledgement, dispatch, and safe-state behavior without a backend or network:

```sh
python3 jetson-agent/simulator.py
```

To simulate an unreachable backend and verify that the agent returns to its
safe state after bounded retries:

```sh
python3 jetson-agent/simulator.py --simulate-lost-connection
```

## Local backend simulation

The backend must have a matching device record and a pending command. Keep
`DRY_RUN=true`, then poll exactly once:

```sh
python3 jetson-agent/simulator.py --backend-once
```

That command sends one heartbeat and one simulated telemetry sample, then
exits. The dashboard will show the device as online first and automatically
change it to offline after `JETSON_HEARTBEAT_TIMEOUT_SECONDS` passes.

Run the continuous Wi-Fi polling loop only after the one-cycle simulation works:

```sh
python3 jetson-agent/agent.py
```

The HTTP client makes at most three attempts for temporary failures, using
bounded exponential backoff. Authentication and protocol failures are not
retried. Exhausted communication attempts immediately activate the safe state.

## Tests

From the repository root, using the existing development environment:

```sh
.venv/bin/python -m pytest jetson-agent/tests -q
```

These are laptop simulations, not real Jetson or GPIO tests. Real hardware must
remain disabled until pin assignments, voltage levels, emergency-stop behavior,
watchdogs, authentication provisioning, and physical fail-safes are reviewed.
The repository-level gate is documented in `../docs/hardware-safety.md`.
