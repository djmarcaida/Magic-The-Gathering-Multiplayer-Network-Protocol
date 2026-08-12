"""Two-seat TCP connection manager; reader threads never mutate game state."""

from __future__ import annotations

import queue
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any

from common.framing import FramingError, recv_pdu, send_pdu


@dataclass(frozen=True)
class ConnectionEvent:
    kind: str
    seat_id: str
    pdu: dict[str, object] | None = None
    error: Exception | None = None


@dataclass
class _Seat:
    sock: socket.socket | None = None
    write_lock: threading.Lock | None = None
    reserved_until: float = 0.0


class ConnectionManager:
    """
    Manages TCP listeners, socket acceptance, and per-client reader threads.

    Enforces the two-seat limit, manages reconnection timeouts, and places
    parsed incoming PDUs and connection lifecycle events onto a shared,
    thread-safe queue for the main engine thread to process.
    """
    def __init__(self, host: str, port: int, event_queue: queue.Queue,
                 verbose: bool = False, reconnect_timeout: float = 30.0):
        self.host = host
        self.port = port
        self.event_queue = event_queue
        self.verbose = verbose
        self.reconnect_timeout = reconnect_timeout
        self.listener: socket.socket | None = None
        self.address: tuple[str, int] = (host, port)
        self.seats = {"seat_1": _Seat(), "seat_2": _Seat()}
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._accept_thread: threading.Thread | None = None

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((self.host, self.port))
            listener.listen(4)
            listener.settimeout(0.2)
        except OSError:
            listener.close()
            raise
        self.listener = listener
        self.address = listener.getsockname()[:2]
        self._accept_thread = threading.Thread(target=self.accept_connections,
                                                name="mtgnp-accept", daemon=True)
        self._accept_thread.start()

    def accept_connections(self) -> None:
        assert self.listener is not None
        while not self._closed.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.settimeout(None)
            with self._lock:
                seat_id = next((sid for sid, seat in self.seats.items()
                                if seat.sock is None), None)
                if seat_id is None:
                    try:
                        send_pdu(conn, {"type": "ERROR", "seq_num": 0,
                                        "code": "ILLEGAL_ACTION",
                                        "message": "server already has two connected players",
                                        "rejected_action": None}, verbose=self.verbose)
                    finally:
                        conn.close()
                    continue
                seat = self.seats[seat_id]
                seat.sock = conn
                seat.write_lock = threading.Lock()
                seat.reserved_until = 0.0
            self.event_queue.put(ConnectionEvent("CONNECTED", seat_id))
            threading.Thread(target=self._reader, args=(seat_id, conn),
                             name=f"mtgnp-reader-{seat_id}", daemon=True).start()

    def _reader(self, seat_id: str, conn: socket.socket) -> None:
        try:
            while not self._closed.is_set():
                try:
                    pdu = recv_pdu(conn, verbose=self.verbose, label=f"RECV {seat_id}")
                except FramingError as exc:
                    if exc.code == "INVALID_JSON":
                        self.event_queue.put(ConnectionEvent("ERROR", seat_id, error=exc))
                        continue
                    raise
                self.event_queue.put(ConnectionEvent("PDU", seat_id, pdu=pdu))
        except (ConnectionError, OSError, FramingError) as exc:
            if not self._closed.is_set():
                self.event_queue.put(ConnectionEvent("DISCONNECTED", seat_id, error=exc))
        finally:
            with self._lock:
                seat = self.seats[seat_id]
                if seat.sock is conn:
                    seat.sock = None
                    seat.write_lock = None
                    seat.reserved_until = time.monotonic() + self.reconnect_timeout
            try:
                conn.close()
            except OSError:
                return

    def send(self, seat_id: str, pdu: dict[str, object]) -> None:
        with self._lock:
            seat = self.seats[seat_id]
            sock, write_lock = seat.sock, seat.write_lock
        if sock is None or write_lock is None:
            raise ConnectionError(f"{seat_id} is disconnected")
        with write_lock:
            send_pdu(sock, pdu, verbose=self.verbose, label=f"SEND {seat_id}")

    def broadcast(self, pdu: dict[str, object]) -> None:
        for seat_id in tuple(self.seats):
            try:
                self.send(seat_id, pdu)
            except ConnectionError:
                continue

    def reserve_disconnected(self, seat_id: str) -> None:
        with self._lock:
            self.seats[seat_id].reserved_until = time.monotonic() + self.reconnect_timeout

    def disconnect(self, seat_id: str) -> None:
        """Close the current occupant while retaining the logical seat."""
        with self._lock:
            sock = self.seats[seat_id].sock
        if sock is None:
            return
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            sock.close()
            return
        sock.close()

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                self.listener = None
        with self._lock:
            sockets = [seat.sock for seat in self.seats.values() if seat.sock is not None]
            for seat in self.seats.values():
                seat.sock = None
                seat.write_lock = None
        for sock in sockets:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                sock.close()
                continue
            sock.close()
        if self._accept_thread and self._accept_thread is not threading.current_thread():
            self._accept_thread.join(timeout=1)
