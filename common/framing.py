"""Length-prefixed JSON framing used by every MTGNP connection."""

from __future__ import annotations

import json
import struct
from collections.abc import Callable, Mapping
from typing import Any

MAX_PDU_BYTES = 65_535


class FramingError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def encode_pdu(pdu: Mapping[str, object]) -> bytes:
    try:
        payload = json.dumps(pdu, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FramingError("INVALID_JSON", f"PDU is not JSON serializable: {exc}") from exc
    if len(payload) > MAX_PDU_BYTES:
        raise FramingError("FRAME_TOO_LARGE", f"PDU exceeds {MAX_PDU_BYTES} bytes")
    return struct.pack("!I", len(payload)) + payload


def recv_exact(sock: Any, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            raise ConnectionError("connection closed while receiving a PDU")
        chunks.extend(chunk)
    return bytes(chunks)


def _log(pdu: Mapping[str, object], label: str, logger: Callable[[str], None]) -> None:
    logger(f"{label} {json.dumps(pdu, ensure_ascii=False, sort_keys=True)}")


def send_pdu(sock: Any, pdu: Mapping[str, object], *, verbose: bool = False,
             label: str = "SEND", logger: Callable[[str], None] = print) -> None:
    sock.sendall(encode_pdu(pdu))
    if verbose:
        _log(pdu, label, logger)


def recv_pdu(sock: Any, *, verbose: bool = False, label: str = "RECV",
             logger: Callable[[str], None] = print) -> dict[str, object]:
    length = struct.unpack("!I", recv_exact(sock, 4))[0]
    if length > MAX_PDU_BYTES:
        raise FramingError("FRAME_TOO_LARGE", f"PDU exceeds {MAX_PDU_BYTES} bytes")
    try:
        decoded = json.loads(recv_exact(sock, length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FramingError("INVALID_JSON", f"Invalid UTF-8 JSON payload: {exc}") from exc
    if not isinstance(decoded, dict):
        raise FramingError("INVALID_JSON", "PDU JSON root must be an object")
    if verbose:
        _log(decoded, label, logger)
    return decoded
