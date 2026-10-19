"""Start Tejas:  python -m tejas_ai

Serves the app on http://localhost:8000 (this computer) and on
https://<this-computer's-ip>:8443 (every other screen at home).
"""
from __future__ import annotations

import argparse
import asyncio
import multiprocessing
import sys

import uvicorn

from . import __version__, certs
from .config import Config, home


def make_servers(host=None, http_port=None, https_port=None, use_https=None):
    """Build the uvicorn servers (plain http for this computer, https for other screens)."""
    root = home()
    cfg = Config(root / "config.json")
    host = host or cfg.get("server.host", "0.0.0.0")
    http_port = http_port or cfg.get("server.http_port", 8000)
    https_port = https_port or cfg.get("server.https_port", 8443)
    if use_https is None:
        use_https = cfg.get("server.https", True)

    from .server import create_app
    app = create_app()
    servers = [uvicorn.Server(uvicorn.Config(app, host=host, port=http_port, log_level="warning"))]
    urls = {"local": f"http://localhost:{http_port}", "lan": []}
    if use_https:
        crt, key, _ = certs.ensure(root / "certs")
        servers.append(uvicorn.Server(uvicorn.Config(app, host=host, port=https_port, log_level="warning",
                                                     ssl_certfile=str(crt), ssl_keyfile=str(key))))
        urls["lan"] = [f"https://{ip}:{https_port}" for ip in certs.lan_ips()]
    return servers, urls


async def serve(servers) -> None:
    await asyncio.gather(*(s.serve() for s in servers))


def main() -> None:
    multiprocessing.freeze_support()
    ap = argparse.ArgumentParser(prog="tejas-ai", description="Tejas AI home assistant")
    ap.add_argument("--host", help="address to listen on (default: all home network addresses)")
    ap.add_argument("--port", type=int, help="plain http port for this computer (default 8000)")
    ap.add_argument("--https-port", type=int, help="https port for other screens (default 8443)")
    ap.add_argument("--no-https", action="store_true", help="only serve plain http")
    args = ap.parse_args()

    servers, urls = make_servers(args.host, args.port, args.https_port, False if args.no_https else None)
    print(f"\n  Tejas AI {__version__}\n  On this computer:   {urls['local']}")
    for u in urls["lan"]:
        print(f"  Phones, TV, tablets: {u}")
    print(f"  Data folder:        {home()}\n  Press Ctrl+C to stop.\n")
    try:
        asyncio.run(serve(servers))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
