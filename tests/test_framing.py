import json
import socket
import struct
import unittest

from common.framing import MAX_PDU_BYTES, FramingError, encode_pdu, recv_pdu, send_pdu


class FramingTests(unittest.TestCase):
    def test_encode_pdu_prefixes_utf8_json_length(self):
        frame = encode_pdu({"type": "PING", "seq_num": 7, "timestamp": 12.5})
        size = struct.unpack("!I", frame[:4])[0]
        self.assertEqual(size, len(frame[4:]))
        self.assertEqual(json.loads(frame[4:]), {"seq_num": 7, "timestamp": 12.5, "type": "PING"})

    def test_recv_pdu_reassembles_fragmented_socket_reads(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        frame = encode_pdu({"type": "PING", "seq_num": 1, "timestamp": 1.0})
        for chunk in (frame[:2], frame[2:5], frame[5:]):
            left.sendall(chunk)
        self.assertEqual(recv_pdu(right)["type"], "PING")

    def test_rejects_oversized_payload_before_send(self):
        with self.assertRaises(FramingError) as raised:
            encode_pdu({"data": "x" * MAX_PDU_BYTES})
        self.assertEqual(raised.exception.code, "FRAME_TOO_LARGE")

    def test_invalid_utf8_is_invalid_json(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        left.sendall(struct.pack("!I", 1) + b"\xff")
        with self.assertRaises(FramingError) as raised:
            recv_pdu(right)
        self.assertEqual(raised.exception.code, "INVALID_JSON")

    def test_verbose_send_logs_readable_pdu_once(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        records = []
        send_pdu(left, {"type": "PING", "seq_num": 1, "timestamp": 2},
                 verbose=True, label="OUT", logger=records.append)
        recv_pdu(right)
        self.assertEqual(len(records), 1)
        self.assertIn('OUT {"seq_num": 1', records[0])


if __name__ == "__main__":
    unittest.main()
