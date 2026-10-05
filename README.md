# Local Jetson Control Application

This project runs a React dashboard, FastAPI backend, SQLite database, and Jetson simulator locally. Bus arrivals use live LTA DataMall data. **Jetson control remains simulation only**: it contains no GPIO, PWM, serial, motor, or actuator output code.

Wi-Fi/HTTP is the working default transport. An optional BLE transport currently consists only of authenticated protocol interfaces and mocks; it does not scan, advertise, connect, or replace Wi-Fi. See [the BLE design and hardware inspection](docs/bluetooth.md).

Expected addresses:

| Service | Address |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend | `http://127.0.0.1:8000` |
| FastAPI documentation | `http://127.0.0.1:8000/docs` |

## Set up a downloaded copy

This repository contains the source, tests, bus-stop directory, dependency files,
and documentation. Each user supplies their own credentials. Local `.env` files,
SQLite databases, HTTPS certificates and keys, virtual environments,
`node_modules`, and generated builds are excluded from Git.

The complete application has been checked with Node.js 24 and Python 3.14 on
macOS. Install those runtimes before following these commands. Open Terminal
inside your downloaded or cloned `LTA` folder:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend ci
test -f backend/.env || cp backend/.env.example backend/.env
test -f frontend/.env || cp frontend/.env.example frontend/.env
test -f jetson-agent/.env || cp jetson-agent/.env.example jetson-agent/.env
```

Create `.venv` only on a fresh copy; reuse an existing environment. Add your own
LTA AccountKey to `backend/.env` for live arrivals. Optionally put your restricted
Google Maps browser key in `frontend/.env.local` as
`VITE_GOOGLE_MAPS_API_KEY=your_key`. To use the simulator, configure two different
backend tokens and a matching device token as described below. Keep `DRY_RUN=true`.

In separate terminals, each opened inside this project folder, start:

```sh
./scripts/start-backend.sh
```

```sh
./scripts/start-frontend.sh
```

```sh
./scripts/start-simulator.sh
```

Open `http://localhost:5173`. These scripts locate the project from their own
paths; the Mac-specific paths later in this guide are examples for the original
development machine. For location access from other devices, generate your own
HTTPS certificates and follow [the local HTTPS guide](docs/local-https.md).
Publishing the repository does not host or start the website.

## First-time configuration

### HTTPS and location access for other devices

Use **HTTPS port 5443** for other devices on the same Wi-Fi to use location.
Run `./scripts/start-frontend-https.sh` with FastAPI running, then open
`https://YOUR_MAC_WIFI_IP:5443`. Every visiting device must first trust the public
local CA certificate. This trust step is not automatic; do not bypass browser
certificate warnings. [Complete HTTPS setup and device instructions](docs/local-https.md).

HTTP port 5173 can stay running separately. Browser API requests now use the
same origin and are forwarded to FastAPI locally, so they work from either URL.

### LTA bus arrivals

In the dashboard's **Bus arrivals** panel, enter a five-digit bus stop code and an optional service number, then select **Show arrivals**. For example, use stop `83139` and service `15`. Leaving the service blank displays all services at that stop. The next three estimates show minutes until arrival, Singapore time, occupancy, and whether the estimate is scheduled or location-based.

The page refreshes automatically every 20 seconds while visible. Refreshes do not overlap; a slow response delays the next request. Updates pause when the tab is hidden and resume immediately when you return. No operator token is needed to look up public bus arrivals. Jetson commands still require the separate operator token.

Set `LTA_API_ACCOUNT_KEY` in your private `backend/.env`, then restart the backend. The browser never receives the key. The Mac needs internet access to contact LTA, but the app and database still run locally. `EXTERNAL_API_MODE=mock` applies only to the older generic external-data endpoints; it does not replace this dedicated LTA integration.

See [LTA integration details](docs/lta-bus-arrivals.md) for the endpoint, caching, missing data, and file locations.

You can also search by stop description or use **Find stops within 500 m**.
**Show Google map** optionally displays all 4,976 directory stops in zoomable
clusters and your permitted location. **Show all stops** resets the map overview;
click a stop marker to load all its services. Google receives map requests only
after you opt in. Its browser-visible demo key is configured in ignored
`frontend/.env.local`; it is separate from the private LTA key. Location on
another device requires trusted HTTPS, even though manual search works on LAN
HTTP. See the integration document for key restrictions, privacy and demo limits.

### Other local settings

Open Terminal and run:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
test -f backend/.env || cp backend/.env.example backend/.env
test -f jetson-agent/.env || cp jetson-agent/.env.example jetson-agent/.env
test -f frontend/.env || cp frontend/.env.example frontend/.env
open -e backend/.env
open -e jetson-agent/.env
```

In `backend/.env`, set `OPERATOR_API_TOKEN` and `JETSON_API_TOKEN` to two different private values. In `jetson-agent/.env`, set `DEVICE_TOKEN` to exactly the same value as backend `JETSON_API_TOKEN`. Keep these settings:

```text
EXTERNAL_API_MODE=mock
DRY_RUN=true
```

The example files contain no secrets. The populated `.env` files are ignored by Git. Do not put the operator token, Jetson token, or external API key in `frontend/.env`.

If dependencies are missing, install them into the project only:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
.venv/bin/python -m pip install -r backend/requirements.txt
npm --prefix frontend install
```

## Daily macOS instructions

Use three Terminal windows: one for FastAPI, one for Vite, and one for the simulator.

### 1. Open the project

Open the folder in Finder:

```sh
open /Users/zhiyao/Documents/Arduino/LTA
```

Move Terminal into the project:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
```

### 2. Activate the existing Python environment

In each Terminal window that will run Python:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
source /Users/zhiyao/Documents/Arduino/LTA/.venv/bin/activate
```

The prompt normally gains a `(.venv)` prefix. The scripts also locate `.venv` themselves, so they do not depend on the current working directory.

### 3. Start FastAPI

In Terminal 1:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
source .venv/bin/activate
./scripts/start-backend.sh
```

Wait for `Application startup complete`. Test it by opening `http://127.0.0.1:8000/health`.

### 4. Start Vite

In Terminal 2:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
./scripts/start-frontend.sh
```

Wait until Vite prints that the local server is ready.

### 5. Start the Jetson simulator

In Terminal 3:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
source .venv/bin/activate
./scripts/start-simulator.sh
```

This continuously sends simulated heartbeats and telemetry and polls for allowlisted commands. Enter the `DEVICE_ID` and backend `OPERATOR_API_TOKEN` in the dashboard. The Jetson token stays in `jetson-agent/.env` and is never entered into the browser.

Useful safe one-shot modes are:

```sh
./scripts/start-simulator.sh --once
./scripts/start-simulator.sh --offline
./scripts/start-simulator.sh --lost-connection
```

### 6. Open the frontend

```sh
open http://localhost:5173
```

### 7. Open FastAPI documentation

```sh
open http://127.0.0.1:8000/docs
```

The backend itself is at `http://127.0.0.1:8000`.

### 8. Run all tests

Stop the development servers first if you want quiet output, then run:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
./scripts/run-tests.sh
```

This runs every Python test, frontend test, lint check, TypeScript check, and production build without activating hardware.

### 9. Find the Mac's local Wi-Fi IP address

First identify the Wi-Fi interface:

```sh
networksetup -listallhardwareports
```

Find the `Hardware Port: Wi-Fi` entry and note its device, commonly `en0`. Then run, replacing `en0` if necessary:

```sh
ipconfig getifaddr en0
```

An address such as `192.168.1.25` is the Mac's current local Wi-Fi address. It can change when the Mac reconnects.

### 10. Configure a Jetson `BACKEND_URL`

For a Jetson on the same trusted Wi-Fi network, change its private `jetson-agent/.env` to use the Mac's current address:

```text
BACKEND_URL="http://192.168.1.25:8000"
DEVICE_ID="jetson-simulator"
DEVICE_TOKEN="the same private value as backend JETSON_API_TOKEN"
DRY_RUN=true
```

Replace `192.168.1.25` with the result from step 9. `localhost` on the Jetson means the Jetson itself, not the Mac.

The Mac backend must listen on the local network for this case. In Terminal 1, use:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
BACKEND_HOST=0.0.0.0 ./scripts/start-backend.sh
```

Continue opening the backend locally with `http://127.0.0.1:8000`. Allow incoming Python connections in the macOS firewall only on a trusted private network. Do not forward port 8000 from the internet or expose it through a public tunnel.

### 11. Stop each program safely

Click each program's Terminal window and press **Control-C**:

1. Stop the simulator first. It enters its simulated safe/off state.
2. Stop Vite.
3. Stop FastAPI last.

Wait for each process to return to the shell prompt. Do not use `kill -9` during normal shutdown.

### 12. Know which mode is running

- `./scripts/start-simulator.sh` uses Wi-Fi/HTTP but all handlers are simulated and outputs stay off.
- `--offline` uses only in-memory data and makes no network request.
- `--lost-connection` deliberately tests the simulated safe state.
- `DRY_RUN=true` is the only accepted mode.
- **Real hardware mode does not exist in this project.** Setting `DRY_RUN=false` is rejected.

The dashboard STOP button is a supervisory software request. It is not a replacement for a physical, hard-wired emergency stop or power disconnect. Wi-Fi must never be the real-time motor-control loop.

## Share the dashboard on the same Wi-Fi network

Find the Mac's current Wi-Fi IP using step 9 above. Browser access now uses a
same-origin proxy: keep this in `frontend/.env` for HTTP and HTTPS:

```text
VITE_API_BASE_URL=/
```

Keep FastAPI running. For **location access**, follow [the certificate trust
setup](docs/local-https.md), start `./scripts/start-frontend-https.sh`, and open
`https://MAC_WIFI_IP:5443` on each trusted device. The HTTPS API health check is
`https://MAC_WIFI_IP:5443/health`. Each device must trust the public CA and grant
location permission; the website cannot grant these permissions for it.

For manual search without remote location access, `./scripts/start-frontend.sh`
still serves `http://MAC_WIFI_IP:5173`. HTTPS can run alongside it on port 5443.
Neither browser path requires exposing backend port 8000 to the LAN or wildcard
CORS: Vite forwards to loopback FastAPI. Direct Jetson Wi-Fi access to FastAPI
remains a separate configuration and is unchanged.

Keep the Mac awake; allow Node through the firewall on the trusted LAN. Guest
networks can block device-to-device traffic. Do not use internet port forwarding.
If the Mac's IP changes, renew its server certificate and restart the HTTPS
frontend as explained in the HTTPS guide. No browser backend IP needs updating.

To limit the frontend to the Mac again, start it with `FRONTEND_HOST=127.0.0.1`
before the applicable start script; stop any existing LAN-bound frontend first.
The operator token still protects commands, and all hardware remains simulated.

## More information

- [System architecture](docs/architecture.md)
- [Optional Bluetooth transport](docs/bluetooth.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Safety checklist](docs/safety-checklist.md)
- [Detailed hardware-safety gate](docs/hardware-safety.md)
