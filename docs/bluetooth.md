# Optional Bluetooth Low Energy transport

## Current status

Bluetooth is **protocol mock only**. Wi-Fi/HTTP remains the active default transport.

No BLE scan, connection, advertisement, GATT registration, or characteristic access was performed. Bleak is not installed in the project environment, and no Jetson was available to inspect. The mock code does not import Bleak or BlueZ bindings.

The intended architecture, after hardware verification, is:

```mermaid
flowchart LR
    Browser["React browser"] -->|"HTTP + operator token"| API["FastAPI on Mac"]
    API -->|"Bleak central/client"| GATT["Jetson BlueZ GATT peripheral"]
    GATT -->|"notifications"]| API
```

There will be no browser Web Bluetooth implementation. Operator authentication remains at FastAPI, and BLE messages additionally use the existing device-only credential.

## Hardware inspection result

| Item | Result on 2026-09-03 |
| --- | --- |
| Mac | Apple M4 MacBook Air (`Mac16,12`), macOS 26.5.1 |
| Mac Bluetooth controller | Built-in controller detected by IOKit with `BluetoothTransportConnected = Yes`; live scanning was not attempted |
| Mac BLE software API | CoreBluetooth framework is present and is the future Bleak backend on macOS |
| Bleak in `.venv` | Not installed |
| Jetson model | Unknown; no target device was accessible |
| Jetson BLE adapter | Unknown |
| Jetson BlueZ version | Unknown; macOS does not use Linux BlueZ |
| Mac Python | 3.14.2 |
| Jetson Python | Unknown |
| Real GATT peripheral support | Unproven and therefore disabled |

## GATT UUID contract

These private 128-bit UUIDs are fixed in both mock implementations:

| Purpose | UUID | Future properties |
| --- | --- | --- |
| LTA service | `8f2d0001-7a4b-4a6b-9c31-2e5d4f7a1000` | Primary service |
| Command characteristic | `8f2d0002-7a4b-4a6b-9c31-2e5d4f7a1000` | FastAPI/Bleak writes; Jetson receives |
| Event characteristic | `8f2d0003-7a4b-4a6b-9c31-2e5d4f7a1000` | Jetson notifies; FastAPI/Bleak subscribes |

The command characteristic accepts only `command` envelopes. The event characteristic carries `heartbeat`, `telemetry`, and `acknowledgement` envelopes.

## Versioned JSON envelope

Protocol version 1 contains exactly these fields:

```json
{
  "protocol_version": 1,
  "message_type": "command",
  "message_id": "00000000-0000-4000-8000-000000000001",
  "correlation_id": null,
  "device_id": "jetson-simulator",
  "created_at": "2026-09-03T12:00:00.000000+00:00",
  "expires_at": "2026-09-03T12:00:30.000000+00:00",
  "payload": {},
  "authentication": {
    "scheme": "hmac-sha256",
    "signature": "64-lowercase-hex-characters"
  }
}
```

- A command's `message_id` is the existing command UUID.
- An acknowledgement has its own acknowledgement UUID as `message_id` and the command UUID as `correlation_id`.
- Other message types must use `correlation_id: null`.
- All timestamps include a UTC offset. Expired messages are rejected before dispatch.
- The signature is HMAC-SHA256 over canonical JSON excluding the `authentication` field, using the device-only token.
- Pairing or link encryption may be required later, but it will supplement rather than replace application authentication.
- Accepted message IDs are held in a bounded replay guard so a complete message cannot be processed twice.

Command payloads remain the existing backend response shape, including `id`, `device_id`, `command_type`, exact payload, `status: "delivered"`, `expires_at`, and `simulation_only: true`. The Jetson's existing independent command validator still runs after BLE envelope validation.

## BLE fragmentation

The mock assumes a conservative 20-byte characteristic value, corresponding to the minimum 23-byte ATT MTU minus three ATT bytes. A future Bleak client may use a larger value only after reading the connection's supported write size.

Each fragment begins with this 12-byte network-order header:

| Bytes | Field |
| --- | --- |
| 1 | Magic value `0x4c` (`L`) |
| 1 | Fragment protocol version `1` |
| 4 | CRC32 message token |
| 2 | Zero-based fragment index |
| 2 | Total fragment count |
| 2 | Payload length in this fragment |

The remaining bytes contain JSON data. Complete JSON messages are limited to 4096 bytes. Reassembly rejects invalid headers, mismatched sizes, repeated fragments, changed fragment counts, checksum mismatches, and oversized data. Incomplete state expires after 10 seconds and is discarded on disconnect. HMAC validation—not CRC32—provides authenticity and tamper protection.

Connection attempts are capped at three by default. No unlimited scan or reconnect loop is permitted.

## Verify the actual Jetson before real implementation

Run these commands on the Jetson and save their complete output:

```sh
tr -d '\000' </proc/device-tree/model
python3 --version
bluetoothctl --version
bluetoothctl list
bluetoothctl show
busctl introspect org.bluez /org/bluez/hci0 org.bluez.GattManager1
busctl introspect org.bluez /org/bluez/hci0 org.bluez.LEAdvertisingManager1
```

Interpretation:

- No controller from `bluetoothctl list` means no usable adapter/driver is visible.
- Missing `GattManager1` means the required GATT application registration interface is unavailable.
- Missing `LEAdvertisingManager1` means the Jetson cannot expose/discoverably advertise the service through that controller.
- A controller must support BLE peripheral/advertising operation, not only central scanning.

Do not install packages, change BlueZ settings, enable experimental flags, or add an adapter until the exact Jetson model and adapter are identified. After that review, the laptop implementation would use Bleak as the central/client; the Jetson peripheral would use the verified BlueZ D-Bus GATT and advertising interfaces.

## Mock code locations

- Backend interface and protocol: `backend/app/transports/base.py`
- Backend Wi-Fi compatibility adapter: `backend/app/transports/wifi.py`
- Backend mock BLE central/framing: `backend/app/transports/bluetooth.py`
- Agent interface and compatible protocol: `jetson-agent/transports/base.py`
- Active agent Wi-Fi wrapper: `jetson-agent/transports/wifi.py`
- Mock GATT peripheral: `jetson-agent/transports/bluetooth.py`

These classes are intentionally not wired into FastAPI routes. That prevents an unverified BLE option from changing or weakening the working Wi-Fi command path.
