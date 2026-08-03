"""MTGNP terminal-client composition root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from client.controller import ClientController
from client.network_client import ClientNetwork
from client.state_store import ClientStateStore
from client.ui import TerminalUI


def load_deck(path: str | Path) -> list[str]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError("deck file must be a JSON array of card instance IDs")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MTGNP terminal client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4444)
    parser.add_argument("--id", required=True, dest="player_id")
    parser.add_argument("--deck", required=True)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)
    network = ClientNetwork(args.host, args.port, verbose=args.verbose,
                            heartbeat_interval=5, heartbeat_timeout=15)
    store = ClientStateStore()
    network.subscribe(store.apply_pdu)
    network.subscribe_disconnect(lambda exc: print(f"Disconnected: {exc}"))
    controller = ClientController(args.player_id, network, store)
    ui = TerminalUI(controller, store)
    network.connect()
    controller.ready(load_deck(args.deck))
    try:
        ui.run()
    finally:
        network.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
