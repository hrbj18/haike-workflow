"""Test-only private configuration and local HTTP server boundary.

Keep the normal venv startup and Backlot CLI/application, while ensuring browser
regressions cannot read an operator's settings or contact external providers.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit


def configure_private(root: Path, *, setter=setattr) -> None:
    """Set the same private stores as pytest's function fixture, before use."""
    from backlot import ai_text, audio_center, avatar_roles, bailian_config

    root = Path(root)
    setter(ai_text, "CONFIG_ROOT", root / "private-config")
    audio = root / "audio"
    setter(audio_center, "AUDIO_CENTER_DIR", audio)
    setter(audio_center, "AUDIO_CENTER_FILE", audio / "audio_center.json")
    setter(audio_center, "PREVIEW_DIRECTORY", audio / "previews")
    setter(bailian_config, "HEALTH_FILE", audio / "bailian-health.json")
    setter(bailian_config, "SELFTEST_DIR", audio / "bailian-tests")
    roles = root / "avatar-roles"
    setter(avatar_roles, "ROLE_DIRECTORY", roles)
    setter(avatar_roles, "ROLE_FILE", roles / "roles.json")
    setter(avatar_roles, "ROLE_ASSET_DIRECTORY", roles / "assets")


def local_browser_url(url: str, server_url: str) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme in {"data", "blob"}:
            return True
        server = urlsplit(server_url)
        scheme = {"ws": "http", "wss": "https"}.get(parsed.scheme, parsed.scheme)
        port = parsed.port if parsed.port is not None else (443 if scheme == "https" else 80)
        server_port = server.port if server.port is not None else (443 if server.scheme == "https" else 80)
        return (
            scheme in {"http", "https"} and scheme == server.scheme
            and parsed.hostname == server.hostname
            and port == server_port
            and parsed.username is None and parsed.password is None
        )
    except ValueError:
        return False


def _loopback_host(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="replace")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def block_external_connections() -> None:
    """Accept incoming HTTP only; never connect even to another local service."""
    def audit(event, args):
        if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"}:
            if not _loopback_host(args[0]):
                raise PermissionError("Browser test child cannot resolve external services")
        elif event in {"socket.connect", "socket.sendto", "socket.sendmsg"}:
            raise PermissionError("Browser test child cannot initiate outbound connections")

    sys.addaudithook(audit)


def _temporary_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(directory / "backlot.log", encoding="utf-8")
    logging.getLogger().addHandler(handler)


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] != "serve":
        raise SystemExit("This test-only entry requires the Backlot serve command")
    # A missing explicit staging directory must fail rather than use real jobs.
    projects = Path(os.environ["OPENMONTAGE_PROJECTS_DIR"]).resolve()
    private = projects.parent / "private"
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["HAIKE_DOWNLOAD_CREDENTIALS_DIR"] = str(private / "download-credentials")
    os.environ["OPENMONTAGE_TTS_DATA_DIR"] = str(private / "tts")
    # Windows asyncio creates its self-wakeup socketpair using a temporary TCP
    # connection. Construct only that loop before the deny-all outbound guard,
    # then let Uvicorn's real Runner own it; application imports happen below.
    loop = asyncio.new_event_loop()
    try:
        block_external_connections()
        configure_private(private)
        from backlot import __main__ as cli
        import uvicorn

        uvicorn.Config.get_loop_factory = lambda self: lambda: loop
        cli._attach_server_logging = lambda: _temporary_logging(private / "logs")
        return cli.main(arguments)
    finally:
        if not loop.is_closed():
            loop.close()


if __name__ == "__main__":
    raise SystemExit(main())
