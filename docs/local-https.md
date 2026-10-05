# HTTPS on the same Wi-Fi network

Yes: other devices can access the locally hosted app and request location.
`http://localhost` is a special secure-context exception, not HTTPS. On a phone,
`localhost` means the phone, not the Mac. Use the Mac's **HTTPS LAN address**.

## How it works

Browser → HTTPS on the Mac, port **5443** → Vite proxy → FastAPI at
`http://127.0.0.1:8000` on the same Mac. Browser API requests use `/api/...`, so
they stay encrypted over Wi-Fi and do not call an HTTP backend URL directly.
FastAPI does not need a second certificate or wildcard CORS. Tokens still apply
to protected API routes. Google Maps remains optional and LTA credentials stay
on the backend. HTTP port 5173 remains available separately for existing users.

This is local development on a trusted LAN, not an internet deployment. Vite
serves development source files: share only with trusted testers. Never forward
these ports on your router. The Mac must stay awake and all devices must be on a
network that permits device-to-device traffic (not an isolated guest network).

## 1. Generate certificates (already done for this Mac's current IP)

From the project root:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
ipconfig getifaddr en0
./scripts/setup-https.sh YOUR_MAC_WIFI_IP
```

Replace `YOUR_MAC_WIFI_IP` with the returned numeric address. If en0 is not your
Wi-Fi interface, find it in System Settings → Wi-Fi → Details → TCP/IP.
The script uses the existing `.venv` and macOS OpenSSL: no global package install,
Homebrew, cloud hosting or automatic certificate trust changes are required.

Files are in ignored `.local-https/`, outside Vite's allowed serving directory:

- `lta-local-ca.crt`: public CA certificate; this is the **only file to share**.
- `ca.key`: private signing key. Never share or upload it.
- `server.crt` and `server.key`: server certificate and private key. Keep on Mac.

Trusting this CA authorizes certificates signed by its private key. Protect that
key and only ask trusted testers to install this certificate. It is not a general
public certificate. Remove this CA from devices when testing ends. If a key is
exposed, stop using that CA and remove its trust from all devices.

Verify the public certificate fingerprint on the Mac before sharing:

```sh
openssl x509 -in .local-https/lta-local-ca.crt -noout -fingerprint -sha256
```

## 2. Trust the public CA on each visiting device (owner action)

Send **only `lta-local-ca.crt`** via AirDrop or another trusted file-transfer
method. Do not put any certificate/key files in `frontend/public`.

- **Hosting Mac / another Mac:** open the public `.crt` in Keychain Access,
  import into the login keychain, inspect **LTA Local Development CA**, and set
  its SSL trust to **Always Trust** after verifying the source/fingerprint. macOS
  may request approval/password. Restart the browser if needed.
- **iPhone/iPad:** accept the public certificate file, install the downloaded
  profile in Settings (General → VPN & Device Management / Profile Downloaded),
  then Settings → General → About → Certificate Trust Settings → enable full
  trust for **LTA Local Development CA**. Installation alone is not enough.
- **Android:** in Settings search for **Install a certificate → CA certificate**
  (usually under Security → Encryption & credentials). Install this public CA,
  then test in Chrome. Names and support vary by device, browser and management
  policy; a managed device may prohibit user-added CAs.
- **Windows:** use the certificate manager to install the public certificate in
  the current user's Trusted Root Certification Authorities after verifying it.
  Firefox may need its own certificate import/trust setting.

Do **not** click through a certificate error or disable browser security. A page
with an untrusted certificate is not a reliable geolocation setup. Device trust
and browser location permissions cannot be granted by website code.

Apple's instructions: https://support.apple.com/en-us/102390

## 3. Start the app

Keep the existing backend running if it already owns port 8000. Otherwise:

```sh
./scripts/start-backend.sh
```

In another terminal:

```sh
cd /Users/zhiyao/Documents/Arduino/LTA
./scripts/start-frontend-https.sh
```

Open **`https://YOUR_MAC_WIFI_IP:5443`** on other devices, or
**`https://localhost:5443`** on the Mac. There must be **no certificate warning**.
Choose **Find stops within 500 m**, then allow the browser's location request.
The OS's Location Services must also be enabled. A desktop computer's location
can be less precise than a phone's GPS location.

API health: `https://YOUR_MAC_WIFI_IP:5443/health`.
API docs: `https://YOUR_MAC_WIFI_IP:5443/docs`.
No need to expose port 8000 just for browsers. A simulator or Jetson's existing
transport is unchanged. If you no longer need direct backend LAN access, start
it with `BACKEND_HOST=127.0.0.1 ./scripts/start-backend.sh`.

If macOS firewall asks, allow Node incoming connections on the trusted LAN;
do not turn off the firewall. Keep operator tokens private; viewing bus arrivals
does not require one. Stop only the HTTPS frontend with Control-C in its terminal.

Google Maps website restrictions must include the exact HTTPS origin you use,
e.g. `https://YOUR_MAC_WIFI_IP:5443/*` and `https://localhost:5443/*`. This browser
map key is separate from LTA's private key. Do not remove key restrictions.

## Changes, renewal and diagnosis

- Server certificates expire after 90 days. If the Wi-Fi IP changes, renew with
  `./scripts/setup-https.sh NEW_MAC_WIFI_IP --renew`, then restart HTTPS Vite.
  This replaces only the server certificate/key and retains the existing CA, so
  clients need not trust a new CA. Consider a DHCP reservation on your router.
- Port 5443 is HTTPS only; port 5173 is HTTP only. Do not interchange the schemes.
- `ERR_CERT_AUTHORITY_INVALID`: the public CA is not trusted by that browser.
- Name/IP mismatch: URL does not match a certificate address; renew as above.
- Cannot connect: check Wi-Fi IP, Mac sleep, firewall and guest/client isolation.
- Backend offline: check FastAPI on port 8000. If using another port, start HTTPS
  with `LTA_BACKEND_PORT=8001 ./scripts/start-frontend-https.sh` (match the backend).
- Location denied: check site permissions and OS Location Services. Trusting the
  certificate does not automatically grant location access.
- Validate TLS without bypassing certificate checks:

  ```sh
  curl --cacert .local-https/lta-local-ca.crt https://YOUR_MAC_WIFI_IP:5443/health
  ```

The start script fails on an occupied port or invalid/missing certificate; it
never silently downgrades to HTTP. Ordinary builds still work without certificates.
A built frontend with relative API URLs needs a same-origin API reverse proxy;
`vite preview` by itself is not the HTTPS/API launcher described here.

If installing a CA on each device is not acceptable, use a domain you own with
a publicly trusted certificate and local DNS pointing to the Mac. This requires
domain/DNS setup; it cannot provide a public certificate for a private numeric IP.
It can remain LAN-only, but is not configured by this change.
