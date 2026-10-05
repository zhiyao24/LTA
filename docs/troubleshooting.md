# Troubleshooting on macOS

Run commands from `/Users/zhiyao/Documents/Arduino/LTA` unless a section says otherwise.

## A script says permission denied

Restore executable permissions:

```sh
chmod +x scripts/*.sh
```

Then try the script again.

## `.venv` or Python is missing

Confirm the existing environment:

```sh
ls -l .venv/bin/python
.venv/bin/python --version
```

This project was verified with Python 3.14. Do not install packages globally. If the environment exists but dependencies are missing:

```sh
.venv/bin/python -m pip install -r backend/requirements.txt
```

## Node, npm, or frontend dependencies are missing

Check the tools and install project dependencies:

```sh
node --version
npm --version
npm --prefix frontend install
```

This project was verified with Node.js 24 and npm 11.

## FastAPI does not start

If `backend/.env` is missing:

```sh
cp backend/.env.example backend/.env
open -e backend/.env
```

Use two different values for `OPERATOR_API_TOKEN` and `JETSON_API_TOKEN`. If they match, startup deliberately fails. Verify the backend environment independently with:

```sh
.venv/bin/python -c 'from backend.app.config import get_settings; print(get_settings())'
```

Secrets are hidden in that representation.

## Port 8000 or 5173 is already in use

Find the existing process:

```sh
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
```

Return to the Terminal running that process and press Control-C. Avoid `kill -9` unless a process cannot shut down normally.

## The frontend says the backend is offline

1. Start `./scripts/start-backend.sh`.
2. On the Mac, open `http://127.0.0.1:8000/health` and confirm a JSON response. On another device, use `https://MAC_WIFI_IP:5443/health` after trusting the local CA.
3. Confirm `frontend/.env` uses the same-origin proxy:

   ```text
   VITE_API_BASE_URL=/
   ```

   Do not put an HTTP backend URL on an HTTPS page. The HTTPS launcher enforces same-origin requests.
4. FastAPI must be reachable on `127.0.0.1:8000` from the Mac. If its port differs, set `LTA_BACKEND_PORT` for the frontend launcher. Browser sharing does not require changing backend CORS or exposing port 8000.
5. Restart Vite after changing `frontend/.env` and restart FastAPI after changing `backend/.env`. Refresh the browser.

Do not change the base setting to `/api`; individual requests already include that path.

## Another device cannot open the dashboard

1. Open `http://MAC_WIFI_IP:5173` using the Mac's current numeric Wi-Fi address. Do not use `localhost` or `0.0.0.0` on the other device.
2. Start Vite with `./scripts/start-frontend.sh`; it listens on the local network by default. An explicit `FRONTEND_HOST=127.0.0.1` override makes it laptop-only.
3. Ensure both devices are on the same network and it allows devices to communicate. Guest Wi-Fi often prevents this.
4. If macOS prompts, allow incoming connections for Node (frontend) and Python (backend). Keep the Mac awake and both Terminal processes running.
5. If the page opens but says backend offline, follow the previous section. Loading the page only verifies the frontend connection.

See [sharing instructions](../README.md#share-the-dashboard-on-the-same-wi-fi-network) for the complete configuration. No router port forwarding is needed.

## Commands, devices, or telemetry return 401 or 503

- Enter backend `OPERATOR_API_TOKEN` in the dashboard, not the Jetson token.
- Set `DEVICE_TOKEN` in `jetson-agent/.env` to backend `JETSON_API_TOKEN`.
- Keep the operator and Jetson tokens different.
- Restart the backend and simulator after changing either file.
- Never put either token in `frontend/.env`.

## The simulator says a setting is missing

Create and edit its private configuration:

```sh
cp jetson-agent/.env.example jetson-agent/.env
open -e jetson-agent/.env
```

For a simulator on the same Mac, use `BACKEND_URL="http://127.0.0.1:8000"`. Set a valid `DEVICE_ID`, matching `DEVICE_TOKEN`, and `DRY_RUN=true`.

## The dashboard shows the Jetson offline

The simulator must keep running. The default heartbeat timeout is 10 seconds, so the dashboard correctly changes to offline soon after it stops. Telemetry becomes stale after 15 seconds by default.

Check the simulator Terminal for authentication or connection messages. You can safely test a single cycle with:

```sh
./scripts/start-simulator.sh --once
```

## A physical Jetson cannot reach the Mac

1. Confirm both devices are on the same trusted Wi-Fi network and client isolation is disabled.
2. Find the Mac's Wi-Fi address with `networksetup -listallhardwareports` and `ipconfig getifaddr en0`.
3. Start FastAPI with `BACKEND_HOST=0.0.0.0 ./scripts/start-backend.sh`.
4. Set the Jetson `BACKEND_URL` to the Mac address, never `localhost`.
5. Allow incoming Python connections in the macOS firewall.
6. Do not use guest Wi-Fi, port forwarding, a public tunnel, or a cloud host.

From the Jetson, a read-only connectivity check is:

```sh
curl http://MAC_WIFI_IP:8000/health
```

Replace `MAC_WIFI_IP` with the actual numeric address.

Do not switch to Bluetooth as a connectivity workaround. BLE is currently mock-only; follow the inspection gate in `docs/bluetooth.md` first.

## Bus arrivals are empty or not updating

- Enter a five-digit bus stop code, including any leading zero, and select **Show arrivals**. Service numbers may contain letters, such as `225G`. Leave the service blank to check all services at the stop.
- `No estimate` means LTA supplied no arrival time. This alone does not prove the bus is not operating; operating-hours data is not part of this integration.
- Set `LTA_API_ACCOUNT_KEY` in `backend/.env` if it is not configured or LTA rejects it. Fully restart the backend after a key change; Python hot reload does not reload shell environment values.
- Keep the Mac connected to the internet. Local Wi-Fi access to the dashboard alone does not provide a connection to LTA.
- Automatic refresh runs every 20 seconds while the tab is visible. Hidden tabs pause; returning to the page triggers an update.
- A stale warning means the previous estimate is being preserved after a failure or missed refresh. It is not a fresh arrival countdown. A new stop/service search never reuses another search's data.
- `EXTERNAL_API_TIMEOUT_SECONDS` controls the LTA request timeout (five seconds by default). Errors use a 20-second cooldown rather than immediate retry loops.

The generic `/api/external/latest` and operator-authenticated `/api/external/refresh` endpoints remain available for the earlier mock/HTTP adapter. The dashboard's bus panel uses the separate `/api/bus-arrivals` endpoint.

## SQLite problems

The development database is `backend/data/lta.db`. Do not delete it as a troubleshooting shortcut. Run database tests against isolated temporary files:

```sh
.venv/bin/python -m pytest backend/tests/test_database.py -q
```

## A test fails

Run the complete gate:

```sh
./scripts/run-tests.sh
```

Read the first failure, correct it, and rerun. Two third-party FastAPI/Starlette deprecation warnings may appear; they are not test failures.
# HTTPS / location on another device

For location access over Wi-Fi use `https://MAC_WIFI_IP:5443`, not HTTP or
`localhost` on that device. Run `scripts/start-frontend-https.sh` and install/trust
the public local CA on each device. See [local HTTPS](local-https.md) for the exact
steps, renewal and certificate errors. The recommended frontend API setting is
now `VITE_API_BASE_URL=/`; Vite proxies requests to local FastAPI. The direct-HTTP
LAN instructions below describe the older optional setup, not HTTPS operation.
