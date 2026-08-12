import queue
import socket
import struct
import time
import unittest

from common.framing import recv_pdu, send_pdu
from server.connection_manager import ConnectionManager


class ConnectionManagerTests(unittest.TestCase):
    def setUp(self):
        self.events = queue.Queue()
        self.manager = ConnectionManager("127.0.0.1", 0, self.events,
                                         reconnect_timeout=0.2)
        self.manager.start()
        self.clients = []

    def tearDown(self):
        for client in self.clients:
            client.close()
        self.manager.close()

    def connect(self):
        client = socket.create_connection(self.manager.address, timeout=1)
        client.settimeout(1)
        self.clients.append(client)
        return client

    def next_kind(self, kind):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            event = self.events.get(timeout=1)
            if event.kind == kind:
                return event
        self.fail(f"no {kind} event")

    def test_two_clients_receive_distinct_seats_and_pdus_are_tagged(self):
        first, second = self.connect(), self.connect()
        seats = {self.next_kind("CONNECTED").seat_id,
                 self.next_kind("CONNECTED").seat_id}
        self.assertEqual(seats, {"seat_1", "seat_2"})
        send_pdu(first, {"type": "PING", "seq_num": 1, "timestamp": 2.0})
        event = self.next_kind("PDU")
        self.assertIn(event.seat_id, seats)
        self.assertEqual(event.pdu["type"], "PING")

    def test_third_connection_is_refused_with_protocol_error(self):
        self.connect(); self.connect()
        self.next_kind("CONNECTED"); self.next_kind("CONNECTED")
        third = self.connect()
        rejection = recv_pdu(third)
        self.assertEqual((rejection["type"], rejection["code"]),
                         ("ERROR", "ILLEGAL_ACTION"))

    def test_second_server_cannot_share_the_same_listening_port(self):
        duplicate = ConnectionManager(*self.manager.address, queue.Queue())
        try:
            with self.assertRaises(OSError):
                duplicate.start()
        finally:
            duplicate.close()

    def test_serialized_sender_delivers_complete_frame(self):
        client = self.connect()
        seat = self.next_kind("CONNECTED").seat_id
        self.manager.send(seat, {"type": "PONG", "seq_num": 9, "timestamp": 3.0})
        self.assertEqual(recv_pdu(client)["seq_num"], 9)

    def test_disconnect_reserves_and_reuses_same_seat(self):
        first = self.connect()
        seat = self.next_kind("CONNECTED").seat_id
        first.close()
        disconnected = self.next_kind("DISCONNECTED")
        self.assertEqual(disconnected.seat_id, seat)
        replacement = self.connect()
        connected = self.next_kind("CONNECTED")
        self.assertEqual(connected.seat_id, seat)
        send_pdu(replacement, {"type": "PING", "seq_num": 4, "timestamp": 5.0})
        self.assertEqual(self.next_kind("PDU").seat_id, seat)

    def test_malformed_json_is_recoverable_for_the_next_frame(self):
        client = self.connect()
        seat = self.next_kind("CONNECTED").seat_id
        client.sendall(struct.pack("!I", 1) + b"{")
        error = self.next_kind("ERROR")
        self.assertEqual((error.seat_id, error.error.code), (seat, "INVALID_JSON"))
        send_pdu(client, {"type": "PING", "seq_num": 6, "timestamp": 1.0})
        recovered = self.next_kind("PDU")
        self.assertEqual((recovered.seat_id, recovered.pdu["seq_num"]), (seat, 6))


if __name__ == "__main__":
    unittest.main()
