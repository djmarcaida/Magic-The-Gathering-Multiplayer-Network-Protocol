"""Threaded TCP transport with callbacks and optional heartbeat."""

from __future__ import annotations

import socket
import threading
import time

from common.framing import recv_pdu, send_pdu


class ClientNetwork:
    def __init__(self, host: str, port: int, *, verbose: bool = False,
                 heartbeat_interval: float = 0.0, heartbeat_timeout: float = 10.0):
        self.host = host
        self.port = port
        self.verbose = verbose
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.sock: socket.socket | None = None
        self._callbacks = []
        self._disconnect_callbacks = []
        self._send_lock = threading.Lock()
        self._closed = threading.Event()
        self._reader_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_seq = 1_000_000
        self.last_pong = time.monotonic()

    def subscribe(self, callback): self._callbacks.append(callback)
    def subscribe_disconnect(self, callback): self._disconnect_callbacks.append(callback)

    def connect(self) -> None:
        if self.sock is not None:
            return
        self.sock = socket.create_connection((self.host, self.port))
        self._reader_thread = threading.Thread(target=self._receive_loop,
                                                name="mtgnp-client-reader", daemon=True)
        self._reader_thread.start()
        if self.heartbeat_interval > 0:
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop,
                                                       name="mtgnp-client-heartbeat", daemon=True)
            self._heartbeat_thread.start()

    def send(self, pdu: dict[str, object]) -> None:
        if self.sock is None:
            raise ConnectionError("client is not connected")
        with self._send_lock:
            send_pdu(self.sock, pdu, verbose=self.verbose, label="SEND")

    def _receive_loop(self) -> None:
        try:
            while not self._closed.is_set():
                pdu = recv_pdu(self.sock, verbose=self.verbose, label="RECV")
                if pdu.get("type") == "PONG":
                    self.last_pong = time.monotonic()
                for callback in tuple(self._callbacks):
                    callback(pdu)
        except (ConnectionError, OSError) as exc:
            if not self._closed.is_set():
                for callback in tuple(self._disconnect_callbacks):
                    callback(exc)

    def _heartbeat_loop(self) -> None:
        while not self._closed.wait(self.heartbeat_interval):
            if time.monotonic() - self.last_pong > self.heartbeat_timeout:
                exc = TimeoutError("server heartbeat timed out")
                for callback in tuple(self._disconnect_callbacks): callback(exc)
                self.close()
                return
            self.send({"type": "PING", "seq_num": self._heartbeat_seq,
                       "timestamp": time.time()})
            self._heartbeat_seq += 1

    def close(self) -> None:
        if self._closed.is_set(): return
        self._closed.set()
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                sock.close()
                return
            sock.close()
