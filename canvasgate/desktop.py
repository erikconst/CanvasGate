"""CanvasGate desktop backend and MCP bridge entry point."""

import argparse
import json
from pathlib import Path
import sys
import threading

from .agent_bridge import AgentConnections, Bridge, PROVIDERS
from .transactions import atomic_bytes
from .web import StudioServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--mcp", choices=PROVIDERS)
    args = parser.parse_args()
    if args.mcp:
        Bridge(args.state, args.mcp).serve()
        return
    if args.vault is None:
        parser.error("--vault is required for desktop mode")
    if args.demo:
        args.vault.mkdir(parents=True, exist_ok=True)
    agents = AgentConnections(args.state, Path(sys.executable))
    server = StudioServer(("127.0.0.1", 0), args.vault, agents=agents, seed_demo=args.demo)
    atomic_bytes(args.state, json.dumps({"port": server.server_port, "token": agents.token}).encode())

    def watch_parent():
        sys.stdin.buffer.read()
        server.shutdown()

    threading.Thread(target=watch_parent, daemon=True).start()
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        server.studio.pool.shutdown(wait=True, cancel_futures=True)
        args.state.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
