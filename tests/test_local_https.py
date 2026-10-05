"""Offline checks: generated cert chain/SANs are verified, not bypassed."""
from pathlib import Path
import ssl

import pytest

from scripts.setup_https import generate, lan_ip


@pytest.mark.parametrize("value", ["8.8.8.8", "127.0.0.1", "0.0.0.0", "::1", "192.168.1.1\nDNS:evil", "example.com"])
def test_setup_rejects_non_lan_addresses(value: str) -> None:
    with pytest.raises(ValueError):
        lan_ip(value)


def handshake(directory: Path, hostname: str) -> None:
    client_context = ssl.create_default_context(cafile=str(directory / "lta-local-ca.crt"))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(directory / "server.crt", directory / "server.key")
    incoming, outgoing, server_in, server_out = (ssl.MemoryBIO() for _ in range(4))
    client = client_context.wrap_bio(incoming, outgoing, server_hostname=hostname)
    server = server_context.wrap_bio(server_in, server_out, server_side=True)
    client_done = server_done = False
    for _ in range(20):
        try:
            client.do_handshake()
            client_done = True
        except ssl.SSLWantReadError:
            pass
        server_in.write(outgoing.read())
        try:
            server.do_handshake()
            server_done = True
        except ssl.SSLWantReadError:
            pass
        incoming.write(server_out.read())
        if client_done and server_done:
            return
    pytest.fail("TLS handshake did not finish")


def test_certificates_verify_ip_and_localhost_preserve_ca_and_require_explicit_renewal(tmp_path: Path) -> None:
    directory = tmp_path / "certs"
    generate(directory, "192.168.88.7")
    original_ca = (directory / "lta-local-ca.crt").read_bytes()
    original_server = (directory / "server.crt").read_bytes()
    for host in ("192.168.88.7", "localhost", "127.0.0.1", "::1"):
        handshake(directory, host)
    with pytest.raises(ssl.SSLCertVerificationError):
        handshake(directory, "192.168.88.8")
    with pytest.raises(ValueError, match="preserved"):
        generate(directory, "192.168.88.8")
    assert original_server == (directory / "server.crt").read_bytes()
    assert (directory / "ca.key").stat().st_mode & 0o777 == 0o600
    assert (directory / "server.key").stat().st_mode & 0o777 == 0o600
    generate(directory, "192.168.88.8", renew=True)
    assert original_ca == (directory / "lta-local-ca.crt").read_bytes()
    handshake(directory, "192.168.88.8")


def test_incomplete_ca_is_never_overwritten(tmp_path: Path) -> None:
    (tmp_path / "ca.key").write_text("existing key")
    with pytest.raises(ValueError, match="Incomplete"):
        generate(tmp_path, "192.168.88.7")
    assert (tmp_path / "ca.key").read_text() == "existing key"
