"""MTGNP server composition root."""

from __future__ import annotations

import argparse
import queue
import threading
import time
from pathlib import Path

from common.cards import CardCatalog
from server.connection_manager import ConnectionEvent, ConnectionManager
from server.game_engine import GameEngine, Outbound

DEFAULT_PORT = 4444


class GameServer:
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 verbose: bool = False, reconnect_timeout: float = 30.0,
                 catalog_path: str | Path | None = None):
        root = Path(__file__).parents[1]
        self.events: queue.Queue[ConnectionEvent] = queue.Queue()
        self.manager = ConnectionManager(host, port, self.events, verbose,
                                         reconnect_timeout)
        self.engine = GameEngine(CardCatalog.from_json(catalog_path or root / "cards.json"))
        self.reconnect_timeout = reconnect_timeout
        self._disconnect_deadlines: dict[str, float] = {}
        self._stopping = threading.Event()

    @property
    def address(self): return self.manager.address

    def start(self) -> None:
        self.manager.start()

    def _deliver(self, outgoing: list[Outbound]) -> None:
        for message in outgoing:
            try:
                if message.recipient is None:
                    self.manager.broadcast(message.pdu)
                else:
                    self.manager.send(message.recipient, message.pdu)
            except ConnectionError:
                continue

    def serve_forever(self) -> None:
        if self.manager.listener is None:
            self.start()
        while not self._stopping.is_set():
            try:
                event = self.events.get(timeout=0.05)
            except queue.Empty:
                event = None
            if event is not None:
                if event.kind == "CONNECTED":
                    # A reserved seat is released only after same-ID PLAYER_READY.
                    # Merely opening a socket must not defeat the reconnect timer.
                    continue
                elif event.kind == "DISCONNECTED":
                    if self.engine.state is not None:
                        self._disconnect_deadlines[event.seat_id] = (
                            time.monotonic() + self.reconnect_timeout)
                elif event.kind == "ERROR" and event.error is not None:
                    code = getattr(event.error, "code", "INVALID_JSON")
                    self._deliver(self.engine.protocol_error(event.seat_id, code,
                                                             str(event.error)))
                elif event.kind == "PDU" and event.pdu is not None:
                    outgoing = self.engine.process(event.seat_id, event.pdu)
                    if (event.pdu.get("type") == "PLAYER_READY"
                            and event.seat_id in self._disconnect_deadlines):
                        if any(item.pdu.get("type") == "ERROR" for item in outgoing):
                            self.manager.disconnect(event.seat_id)
                        else:
                            self._disconnect_deadlines.pop(event.seat_id, None)
                    self._deliver(outgoing)
            now = time.monotonic()
            expired = [seat for seat, deadline in self._disconnect_deadlines.items()
                       if now >= deadline]
            for seat in expired:
                self._disconnect_deadlines.pop(seat, None)
                self._deliver(self.engine.connection_lost(seat))

    def stop(self) -> None:
        self._stopping.set()
        self.manager.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MTGNP authoritative two-player server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--reconnect-timeout", type=float, default=30.0)
    args = parser.parse_args(argv)
    server = GameServer(args.host, args.port, args.verbose, args.reconnect_timeout)
    server.start()
    print(f"MTGNP server listening on {server.address[0]}:{server.address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server.")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
