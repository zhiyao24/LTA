"""Generate project-local TLS files; never modify a system trust store."""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def lan_ip(value: str) -> str:
    """Only accept explicit RFC1918 IPv4 addresses, not arbitrary OpenSSL config."""
    address = ipaddress.IPv4Address(value)
    ranges = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if not any(address in ipaddress.IPv4Network(network) for network in ranges):
        raise ValueError("Use the Mac's private Wi-Fi IPv4 address (10.x, 172.16–31.x, or 192.168.x).")
    return str(address)


def generate(directory: Path, address: str, *, renew: bool = False) -> None:
    """Preserve an existing CA and require explicit opt-in to renew server files."""
    address = lan_ip(address)
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("OpenSSL was not found; macOS normally provides /usr/bin/openssl.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    ca = directory / "lta-local-ca.crt"
    ca_key = directory / "ca.key"
    if ca.exists() != ca_key.exists():
        raise ValueError("Incomplete CA files. Restore the existing CA pair; it will not be replaced.")
    if any((directory / name).exists() for name in ("server.crt", "server.key")) and not renew:
        raise ValueError("Existing server certificate preserved. Use --renew only to renew it or update the Wi-Fi IP.")

    def run(*args: str) -> None:
        result = subprocess.run([openssl, *args], capture_output=True, timeout=30, check=False)
        if result.returncode:
            raise ValueError("Certificate generation/validation failed. Existing installed server files were preserved.")

    # Temporary key files are only created within a private project directory.
    with tempfile.TemporaryDirectory(dir=directory) as temp:
        work = Path(temp)
        config = work / "openssl.cnf"
        config.write_text(f"""[req]
prompt = no
distinguished_name = dn
[dn]
CN = LTA Local Development
[ca_extensions]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
[server_extensions]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid,issuer
subjectAltName = DNS:localhost,IP:127.0.0.1,IP:::1,IP:{address}
""", encoding="utf-8")
        if not ca.exists():
            run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "3650",
                "-subj", "/CN=LTA Local Development CA", "-config", str(config), "-extensions", "ca_extensions",
                "-keyout", str(work / "ca.key"), "-out", str(work / "ca.crt"))
            (work / "ca.key").chmod(0o600)
            (work / "ca.key").replace(ca_key)
            (work / "ca.crt").replace(ca)
        run("x509", "-in", str(ca), "-noout", "-checkend", str(91 * 86400))
        run("req", "-new", "-newkey", "rsa:2048", "-nodes", "-sha256", "-config", str(config),
            "-keyout", str(work / "server.key"), "-out", str(work / "server.csr"))
        run("x509", "-req", "-in", str(work / "server.csr"), "-CA", str(ca), "-CAkey", str(ca_key),
            "-set_serial", f"0x{secrets.token_hex(16)}", "-days", "90", "-sha256",
            "-extfile", str(config), "-extensions", "server_extensions", "-out", str(work / "server.crt"))
        run("verify", "-CAfile", str(ca), str(work / "server.crt"))
        (work / "server.key").chmod(0o600)
        (work / "server.key").replace(directory / "server.key")
        (work / "server.crt").replace(directory / "server.crt")
    ca_key.chmod(0o600)
    print(f"HTTPS certificate ready for https://{address}:5443 and https://localhost:5443 (90 days).")
    print(f"Public CA certificate to install on visiting devices: {ca}")
    print("Trust stores were NOT changed. Never share ca.key or server.key. See docs/local-https.md.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wifi_ip", help="Mac's current Wi-Fi IP; find it with ipconfig getifaddr en0")
    parser.add_argument("--renew", action="store_true", help="Replace server cert/key only, retaining the existing CA")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        generate(PROJECT_ROOT / ".local-https", args.wifi_ip, renew=args.renew)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"HTTPS setup failed: {error}\n")


if __name__ == "__main__":
    main()
