# LTA DataMall bus arrivals

Implemented against section 2.1 of the supplied **LTA DataMall API User Guide v6.9 (3 August 2026)**. Public documentation: https://datamall.lta.gov.sg/content/datamall/en.html.

## Configuration and credentials

- Provider: `https://datamall2.mytransport.sg/ltaodataservice/v3/BusArrival`.
- Backend configuration: `LTA_API_ACCOUNT_KEY` in `backend/.env`.
- Authentication: the backend sends the key in the `AccountKey` request header, never a query string or browser request.
- Request timeout: `EXTERNAL_API_TIMEOUT_SECONDS`, default five seconds, applies to connect/read/write/pool timeouts.
- The LTA HTTPS destination is fixed in `backend/app/config.py`. Redirects are not followed, so the key is not forwarded to another host.
- `backend/.env` is ignored by Git. The `.env.example`, test fixtures, frontend, and documentation contain no real key.
- Restart `./scripts/start-backend.sh` after changing the key. If port 8000 is already in use, stop the existing backend first instead of starting a second copy.

## Using the dashboard

1. Open the dashboard on the Mac or its current LAN address.
2. Enter **Bus stop code**, for example `83139`. Keep leading zeros in codes such as `01219`.
3. Enter **Service number**, for example `15`, or leave it blank for all services. Suffixes such as `225G` and `225W` are kept distinct.
4. Select **Show arrivals**. Once tracking begins, no further clicks are needed.

Each visible search refreshes every 20 seconds after the preceding request finishes. Requests never overlap. A changed search cancels the old request and clears its displayed result. A hidden tab pauses polling and its countdown timer; returning triggers a fresh read.

The next three buses show estimates rounded down to minutes, or **Arriving** when less than one minute remains. A past estimate displays **Updating...**, not a negative or fabricated zero-minute arrival. Absolute times use Asia/Singapore regardless of the viewer's timezone. The countdown uses the backend clock to reduce errors from a misconfigured browser clock.

`Monitored=0` appears as **Scheduled estimate**; `Monitored=1` appears as **Location-based estimate**. Occupancy and wheelchair accessibility use text labels, so color is not the only indicator.

Blank bus slots display **No estimate**. An empty service list displays **No arrival estimates available**. The app does not infer "not operating" because bus-route operating hours are not fetched.

## Local API and persistence

`GET /api/bus-arrivals?bus_stop_code=83139&service_no=15`

The service parameter is optional. Inputs are validated before any upstream request. Successful responses include the stop/service, three slots per service, `received_at`, `server_time`, `is_stale`, and `refresh_interval_seconds: 20`. Browser caching is disabled; the backend manages its shared cache.

SQLite stores only validated, relevant LTA fields in `external_api_snapshots`, under a source such as `lta-bus-arrival:83139:15`. The query identity prevents one stop's results from being shown for another stop. Multiple browsers reuse the same snapshot within 20 seconds. A single service lock prevents duplicate simultaneous upstream fetches in the default one-worker backend.

Only the most recent 1,000 bus snapshots are retained. Existing non-bus snapshots are preserved. The failure cooldown map holds at most 128 query entries. Deploying multiple backend workers is not part of this local setup; the in-memory coordination is per process.

Provider authentication errors, rate limits, timeouts, invalid JSON, invalid timestamps, redirects, wrong-stop/service responses, and server failures receive safe messages. No provider response body or account key is echoed. Each attempt makes a single upstream request; repeated failures wait at least 20 seconds per tracked query before retrying.

After a failed refresh, an existing result is returned with `is_stale: true` and its original receipt time. React shows a warning and labels the old absolute estimate without a live countdown. If no saved result exists, the endpoint returns the standard structured error response. The frontend also marks data stale after two missed 20-second refresh intervals.

## Code and tests

- `backend/app/services/bus_arrivals.py`: LTA requests, cache, failure handling and normalization.
- `backend/app/schemas/bus_arrivals.py`: provider validation and frontend response types.
- `backend/app/routers/bus_arrivals.py`: local query endpoint.
- `backend/app/repositories/external_data_repository.py`: SQLite storage and bounded bus retention.
- `frontend/src/components/BusArrivalPanel.tsx`: search form, polling and arrival cards.
- `frontend/src/utils/busArrivals.ts`: validation, arrival labels and Singapore time formatting.
- `frontend/src/hooks/usePolling.ts`: cancellation, visibility pauses and query-change cleanup.
- `backend/tests/test_bus_arrivals.py` and `frontend/tests/busArrivals.test.ts`: mocked tests; no real key or provider call is required to run them.

Run `./scripts/run-tests.sh` from the project root. Bus lookups are public reads on the local app; command/device authentication is unchanged. LTA data is real, while all Jetson actions remain simulated.
# Stop search and nearby stops

Search by description, road name or bus stop code, then choose a result to load
all services returned by LTA for that stop. The next three estimates continue to
refresh every 20 seconds while the tab is visible. The service field can still
be used to narrow the selected stop to one service.

The directory in `frontend/public/BusStops.json` is the user-supplied snapshot
(4,976 records), not a live directory. Replace it with an updated file with the
same structure when needed. Codes with leading zeros are preserved. Seven
alphanumeric codes are included in search/nearby results but marked unavailable
for arrival lookup because the current arrival API requires five numeric digits.

“Find stops within 500 m” requests browser location permission only when clicked.
Coordinates are not persisted and are not sent to our backend. If the optional
Google map is enabled, they are given to Google's renderer, which sends map
requests and viewport information to Google. The browser/OS may also use its own positioning service. Stops are ordered
by straight-line distance, not walking distance. The reported accuracy is shown;
an imprecise location may omit nearby stops. No continuous tracking is used.

Browser geolocation requires a secure context: use `http://localhost:5173` on
the hosting Mac. On another device, plain HTTP at the Mac's LAN IP does **not**
qualify; use the [HTTPS LAN launcher and certificate trust setup](local-https.md)
on port 5443 before nearby search can work there.
Do not disable browser security. Manual name/code search continues to work on
LAN HTTP, when permission is denied, or when positioning is unavailable.

The picker is in `frontend/src/components/BusStopPicker.tsx`; search, validation
and distance calculations are in `frontend/src/utils/busStops.ts`.

## Optional 2D Google map

Click **Show Google map** to opt in. No Google script or map request is made
before that click. The map includes all 4,976 stops in the supplied directory,
independently of search or the 500 m filter used by the list. Nearby markers are
grouped into count clusters when zoomed out; click a cluster or zoom in to see
individual stop-code markers. **Show all stops** returns to the full directory
view. Selecting a list result centres the map on that stop. Click a stop-code marker
to request all services from FastAPI; arrival polling still runs every 20 seconds.
The map does not reload on each arrival refresh. No location permission is
requested by opening the map itself: use **Find stops within 500 m** separately.

The user marker is labelled “You are here”. The green circle is the 500 m search
radius, not a walking route; the blue area shows reported location accuracy.
Without location, the map fits all directory stops around Singapore. A location
search focuses on the user's 500 m radius without removing any stop markers.
Map errors never disable manual search or the stop list. Hide removes the map
and markers; the already-loaded Google script remains until the page is reloaded.

Configuration: put `VITE_GOOGLE_MAPS_API_KEY` in **frontend/.env.local**, which
is ignored by Git. Restart Vite after changing it. This is an intentionally
browser-visible key and will appear in the compiled frontend and Google script
request. This exception does not apply to LTA, operator or device credentials.
Never commit the populated file or build output.

The supplied demo key and `DEMO_MAP_ID` are for prototyping. Google imposes daily
demo quotas. For production, use your own map ID and appropriately configured
Maps JavaScript API project/key. In Google Cloud, restrict your browser key to
Maps JavaScript API and the exact website origins you use, e.g.
`http://localhost:5173/*`, `http://127.0.0.1:5173/*`, and your actual LAN/HTTPS
host. These restrictions must be configured by the key owner; the application
cannot apply them. Do not allow arbitrary websites or bypass certificate warnings.
The map can work over LAN HTTP, but geolocation still requires trusted HTTPS
on other devices. The optional HTTPS launcher is documented in [local-https.md](local-https.md); nothing is deployed to the cloud.

Files: `BusStopMap.tsx` owns the map lifecycle, `api/googleMaps.ts` loads the
script once with a bounded timeout, and `utils/mapOverlays.ts` manages markers,
circles and their cleanup. Google's `@googlemaps/markerclusterer` groups the full
directory efficiently. The stop layer is built once per map/directory load;
arrival polling, list searches and selection do not rebuild thousands of markers.
The directory remains a user-supplied snapshot, not a guarantee of current coverage.

Official references: [API loading](https://developers.google.com/maps/documentation/javascript/load-maps-js-api),
[demo key](https://developers.google.com/maps/documentation/javascript/demo-key),
[key security](https://developers.google.com/maps/api-security-best-practices).
