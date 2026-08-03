"""Real-socket two-client smoke demo using only public client APIs."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
import json
from pathlib import Path

from client.controller import ClientController
from client.network_client import ClientNetwork
from client.state_store import ClientStateStore
from server.main import GameServer

ROOT = Path(__file__).parents[1]
RED_DECK = json.loads((ROOT / "decks" / "red.json").read_text(encoding="utf-8"))
BLUE_DECK = json.loads((ROOT / "decks" / "blue.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class DemoResult:
    observed_pdu_types: tuple[str, ...]
    winner: str
    reason: str
    restart_state: str


def _wait(predicate, label: str, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.01)
    raise TimeoutError(f"demo timed out waiting for {label}")


def run_demo(host: str = "127.0.0.1", port: int = 0) -> DemoResult:
    server = GameServer(host, port)
    server.start()
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    clients: list[ClientNetwork] = []
    observed: list[dict[str, object]] = []
    try:
        stores, controllers = [], []
        for player_id in ("player_1", "player_2"):
            network = ClientNetwork(*server.address)
            store = ClientStateStore()
            network.subscribe(lambda pdu, s=store: (observed.append(pdu), s.apply_pdu(pdu)))
            network.connect()
            clients.append(network); stores.append(store)
            controllers.append(ClientController(player_id, network, store))
        controllers[0].ready(RED_DECK); controllers[1].ready(BLUE_DECK)
        _wait(lambda: all(s.state.get("lifecycle") == "MULLIGAN" for s in stores), "mulligan")
        old_seq = stores[1].last_server_seq
        controllers[0].keep()
        _wait(lambda: stores[1].last_server_seq != old_seq, "first keep update")
        controllers[1].keep()
        _wait(lambda: all(s.state.get("lifecycle") == "PLAYING" for s in stores), "game start")
        controllers[0].concede()
        _wait(lambda: any(x.get("type") == "GAME_OVER" for x in observed), "game over")
        game_over = next(x for x in observed if x.get("type") == "GAME_OVER")
        controllers[0].ready(RED_DECK); controllers[1].ready(BLUE_DECK)
        _wait(lambda: sum(x.get("type") == "GAME_STATE_UPDATE" and
                          x.get("state", {}).get("lifecycle") == "MULLIGAN"
                          for x in observed) >= 4, "restart")
        return DemoResult(tuple(x["type"] for x in observed), game_over["winner_id"],
                          game_over["reason"], "MULLIGAN")
    finally:
        for client in clients: client.close()
        server.stop(); server_thread.join(timeout=1)


if __name__ == "__main__":
    result = run_demo()
    print("Observed:", ", ".join(result.observed_pdu_types))
    print(f"Winner: {result.winner} ({result.reason}); restart={result.restart_state}")
