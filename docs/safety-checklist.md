# Simulation safety checklist

Use this checklist before each local session.

## Before starting

- [ ] Confirm no actuator, motor driver, relay, GPIO load, or other output hardware is connected or enabled.
- [ ] Confirm `DRY_RUN=true` in `jetson-agent/.env`.
- [ ] Confirm `EXTERNAL_API_MODE=mock` unless a real provider adapter has been explicitly reviewed.
- [ ] Confirm backend `OPERATOR_API_TOKEN` and `JETSON_API_TOKEN` are non-empty and different.
- [ ] Confirm Jetson `DEVICE_TOKEN` matches only backend `JETSON_API_TOKEN`.
- [ ] Confirm no key or device token appears in `frontend/.env` or any `VITE_` variable.
- [ ] Use the default `BACKEND_HOST=127.0.0.1` unless same-Wi-Fi Jetson access is deliberately required.
- [ ] Keep Wi-Fi as the configured transport; BLE is mock-only and must not be enabled.
- [ ] Run `./scripts/run-tests.sh` after safety-related changes.

## While running

- [ ] Treat all displayed speeds and modes as simulated values only.
- [ ] Keep the simulator Terminal visible for connection and safe-state messages.
- [ ] Expect controls to lock when the simulator is offline.
- [ ] Do not add or submit shell commands, Python expressions, terminal input, or unknown command types.
- [ ] Remember that software STOP is not a physical emergency stop or power disconnect.
- [ ] Use Wi-Fi only for supervisory commands and telemetry, never a real-time motor-control loop.

## If communication is lost

- [ ] Verify the simulator reports `communication_lost` or an offline device state.
- [ ] Verify simulated outputs are off and speed returns to zero.
- [ ] Do not assume an unknown physical output is safe based only on a missing heartbeat.
- [ ] Restore communication and inspect command history before submitting another command.

## Safe shutdown

- [ ] Press Control-C in the simulator Terminal first and wait for the prompt.
- [ ] Stop Vite with Control-C.
- [ ] Stop FastAPI with Control-C.
- [ ] Do not use forced termination during normal operation.

## Gate for future physical hardware

Real hardware control remains prohibited until every question and evidence item in [hardware-safety.md](hardware-safety.md) is completed and explicitly reviewed. At minimum this requires an independent physical emergency stop, local deterministic controller, watchdogs, electrical safe-state design, limits/interlocks, fault-injection testing, and an approved first-power procedure.

Real BLE also remains prohibited until [bluetooth.md](bluetooth.md) confirms the exact Jetson model, adapter peripheral support, BlueZ version, `GattManager1`, and `LEAdvertisingManager1`.
