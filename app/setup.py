"""Create first-run local connection credentials for PiAgent."""

import argparse
import ipaddress
import os
import secrets
import socket
import sys
import tempfile
from pathlib import Path
from typing import TextIO

from app.core.security import hash_token, is_valid_token_hash

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def validate_pi_host(host: str) -> str:
    """Accept only an RFC1918 IPv4 address reachable on a private LAN."""
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ValueError("Pi host must be a private IPv4 address.") from error
    if address.version != 4 or not any(address in network for network in _PRIVATE_NETWORKS):
        raise ValueError("Pi host must be an RFC1918 private IPv4 address.")
    return str(address)


def discover_pi_host() -> str:
    """Find a private IPv4 address assigned to the Pi's host name."""
    try:
        addresses = socket.getaddrinfo(
            socket.gethostname(),
            None,
            family=socket.AF_INET,
            type=socket.SOCK_DGRAM,
        )
    except OSError as error:
        raise ValueError(
            "Could not detect a private network address; pass --host <Pi-private-IPv4>."
        ) from error

    for address_info in addresses:
        try:
            return validate_pi_host(address_info[4][0])
        except ValueError:
            continue
    raise ValueError(
        "No private network address was detected; connect the Pi to Wi-Fi or pass "
        "--host <Pi-private-IPv4>."
    )


def _write_hash_once(env_file: Path, token_hash: str) -> None:
    """Create a private env file without replacing an existing file."""
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{env_file.name}.",
        suffix=".tmp",
        dir=env_file.parent,
    )
    temporary_file = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(f"AGENT_TOKEN_HASH={token_hash}\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary_file, env_file)
        except FileExistsError as error:
            raise ValueError(
                f"{env_file} already exists; refusing to overwrite existing configuration."
            ) from error
    finally:
        temporary_file.unlink(missing_ok=True)


def _rotate_hash(env_file: Path, token_hash: str) -> None:
    """Replace a setup-managed token hash without clobbering other settings."""
    if env_file.is_symlink():
        raise ValueError(f"{env_file} must not be a symbolic link.")
    try:
        current = env_file.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise ValueError(f"{env_file} does not exist; run setup without --rotate first.") from error
    lines = current.splitlines()
    if (
        len(lines) != 1
        or not lines[0].startswith("AGENT_TOKEN_HASH=")
        or not is_valid_token_hash(lines[0].partition("=")[2])
    ):
        raise ValueError(
            f"{env_file} is not a setup-managed token-only file; refusing to replace it."
        )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{env_file.name}.",
        suffix=".tmp",
        dir=env_file.parent,
    )
    temporary_file = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(f"AGENT_TOKEN_HASH={token_hash}\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            os.chmod(temporary_file, 0o600)
        os.replace(temporary_file, env_file)
    finally:
        temporary_file.unlink(missing_ok=True)


def configure_connection(
    env_file: Path,
    host: str,
    port: int,
    *,
    rotate: bool = False,
) -> tuple[str, str]:
    """Write the token digest once and return the address and one-time token."""
    resolved_host = validate_pi_host(host)
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    if rotate:
        _rotate_hash(env_file, token_hash)
    else:
        _write_hash_once(env_file, token_hash)
    return f"ws://{resolved_host}:{port}/ws/agent", token


def main(argv: list[str] | None = None, output: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a one-time PiAgent connection token and local WebSocket address.",
    )
    parser.add_argument(
        "--host",
        help="Pi's private IPv4 address (auto-detected from the host name if omitted).",
    )
    parser.add_argument("--port", type=int, default=8000, help="Agent port (default: 8000).")
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Revoke the old token and replace a setup-managed .env token hash.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="New private environment file path (default: .env).",
    )
    args = parser.parse_args(argv)
    stream = output or sys.stdout

    try:
        host = validate_pi_host(args.host) if args.host else discover_pi_host()
        address, token = configure_connection(
            args.env_file,
            host,
            args.port,
            rotate=args.rotate,
        )
    except (OSError, ValueError) as error:
        parser.exit(2, f"PiAgent setup failed: {error}\n")

    print("PiAgent connection setup complete.", file=stream)
    print(f"WebSocket address: {address}", file=stream)
    print(f"Access token (shown once; save it in the phone app): {token}", file=stream)
    print(f"Pi stores only the token hash in {args.env_file}.", file=stream)
    if args.rotate:
        print("The previous token is revoked; restart the PiAgent service now.", file=stream)
    print(
        "Security: this is a strong bearer token, not an 8-digit code. "
        "Use ws:// only on a trusted, isolated private network; TLS is not configured.",
        file=stream,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
