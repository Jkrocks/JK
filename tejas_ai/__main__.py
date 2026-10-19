"""Start Tejas:  python -m tejas_ai

Serves the app on http://localhost:8000 (this computer) and on
https://<this-computer's-ip>:8443 (every other screen at home).
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import uvicorn

from . import __version__, certs
from .config import Config, home


def main() -> None:
    ap = argparse.ArgumentParser(prog="tejas-ai", description="Tejas AI home assistant")
    ap.add_argument("--host", help="address to listen on (default: all home network addresses)")
    ap.add_argument("--port", type=int, help="plain http port for this computer (default 8000)")
    ap.add_argument("--https-port", type=int, help="https port for other screens (default 8443)")
    ap.add_argument("--no-https", action="store_true", help="only serve plain http")
    args = ap.parse_args()

    root = home()
    cfg = Config(root / "config.json")
    host = args.host or cfg.get("server.host", "0.0.0.0")
    http_port = args.port or cfg.get("server.http_port", 8000)
    https_port = args.https_port or cfg.get("server.https_port", 8443)
    use_https = cfg.get("server.https", True) and not args.no_https

    from .server import create_app
    app = create_app()

    servers = [uvicorn.Server(uvicorn.Config(app, host=host, port=http_port, log_level="warning"))]
    print(f"\n  Tejas AI {__version__}\n  On this computer:   http://localhost:{http_port}")
    if use_https:
        crt, key, _ = certs.ensure(root / "certs")
        servers.append(uvicorn.Server(uvicorn.Config(app, host=host, port=https_port, log_level="warning",
                                                     ssl_certfile=str(crt), ssl_keyfile=str(key))))
        for ip in certs.lan_ips():
            print(f"  Phones, TV, tablets: https://{ip}:{https_port}")
    print(f"  Data folder:        {root}\n  Press Ctrl+C to stop.\n")

    async def run():
        await asyncio.gather(*(s.serve() for s in servers))

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
