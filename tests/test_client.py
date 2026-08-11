import socket
import threading
import unittest
from unittest.mock import Mock, patch

from client.controller import ClientController
from client.network_client import ClientNetwork
from client.state_store import ClientStateStore
from client.ui import parse_command
from common.framing import recv_pdu, send_pdu


class RecordingSender:
    def __init__(self): self.sent = []
    def send(self, pdu): self.sent.append(pdu)


class ClientLayerTests(unittest.TestCase):
    def test_state_update_replaces_snapshot_and_notifies_subscriber(self):
        seen = []
        store = ClientStateStore()
        store.subscribe_state(seen.append)
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 8,
                         "state": {"phase": "UPKEEP"}})
        self.assertEqual(store.state, {"phase": "UPKEEP"})
        self.assertEqual(seen[-1]["phase"], "UPKEEP")

    def test_events_errors_and_priority_tokens_use_separate_subscriptions(self):
        store = ClientStateStore()
        events, errors = [], []
        store.subscribe_event(events.append)
        store.subscribe_error(errors.append)
        store.apply_pdu({"type": "PRIORITY_GRANT", "seq_num": 9,
                         "player_id": "p1", "time_limit_ms": 1000})
        store.apply_pdu({"type": "ERROR", "seq_num": 10, "code": "WRONG_PHASE",
                         "message": "no", "rejected_action": None})
        self.assertEqual(store.priority_token, 9)
        self.assertEqual(events[0]["type"], "PRIORITY_GRANT")
        self.assertEqual(errors[0]["code"], "WRONG_PHASE")

    def test_controller_uses_latest_priority_token(self):
        sender, store = RecordingSender(), ClientStateStore()
        store.apply_pdu({"type": "PRIORITY_GRANT", "seq_num": 9,
                         "player_id": "p1", "time_limit_ms": 1000})
        ClientController("p1", sender, store).pass_priority()
        self.assertEqual(sender.sent[-1], {"type": "PRIORITY_PASS", "seq_num": 9})

    def test_heartbeat_pong_does_not_replace_mulligan_request_token(self):
        sender, store = RecordingSender(), ClientStateStore()
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 8,
                         "state": {"lifecycle": "MULLIGAN"}})
        store.apply_pdu({"type": "PONG", "seq_num": 1_000_000, "timestamp": 1.0})

        ClientController("p1", sender, store).keep()

        self.assertEqual(sender.sent[-1]["seq_num"], 8)

    def test_controller_builds_ready_land_cast_and_concede_pdus(self):
        sender, store = RecordingSender(), ClientStateStore()
        controller = ClientController("p1", sender, store)
        controller.ready(["mountain_001"])
        controller.play_land("mountain_001")
        controller.cast_spell("lightning_bolt_001", ["p2"], {"R": 1})
        controller.concede()
        self.assertEqual([x["type"] for x in sender.sent],
                         ["PLAYER_READY", "PLAY_LAND", "CAST_SPELL", "CONCEDE"])

    def test_command_parser_covers_required_commands_and_quotes(self):
        names = ["ready", "keep", "mulligan", "land", "cast", "activate", "pass",
                 "attack", "block", "damage-order", "trigger-order", "trigger-choice",
                 "discard", "concede", "state", "help", "quit"]
        for name in names:
            with self.subTest(name=name):
                self.assertEqual(parse_command(name).name, name)
        self.assertEqual(parse_command('cast bolt "player two"').args,
                         ("bolt", "player two"))

    def test_network_client_receives_and_sends_framed_pdus(self):
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(("127.0.0.1", 0)); listener.listen(1)
        received = []
        network = ClientNetwork(*listener.getsockname()[:2])
        network.subscribe(received.append)
        network.connect()
        server_sock, _ = listener.accept()
        self.addCleanup(server_sock.close)
        self.addCleanup(network.close)
        send_pdu(server_sock, {"type": "PONG", "seq_num": 2, "timestamp": 1.0})
        deadline = threading.Event()
        for _ in range(100):
            if received: break
            deadline.wait(0.01)
        self.assertEqual(received[0]["type"], "PONG")
        network.send({"type": "PING", "seq_num": 3, "timestamp": 2.0})
        self.assertEqual(recv_pdu(server_sock)["seq_num"], 3)

    def test_network_client_discards_a_socket_that_finishes_connecting_after_close(self):
        network = ClientNetwork("127.0.0.1", 4444)
        late_socket = Mock()

        def finish_after_close(_address):
            network.close()
            return late_socket

        with patch("client.network_client.socket.create_connection",
                   side_effect=finish_after_close), self.assertRaisesRegex(
                       ConnectionError, "closed while connecting"):
            network.connect()

        self.assertIsNone(network.sock)
        late_socket.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
