import unittest

from client.state_store import ClientStateStore


class ClientStateStoreTests(unittest.TestCase):
    def test_priority_grant_marks_the_holder_in_the_projection_and_notifies_state(self):
        store = ClientStateStore()
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 5, "state": {
            "lifecycle": "PLAYING", "phase": "UNTAP", "active_player": "p1",
            "priority_holder": None, "priority_token": None,
        }})
        seen = []
        store.subscribe_state(lambda state: seen.append(dict(state)))

        store.apply_pdu({"type": "PRIORITY_GRANT", "seq_num": 9,
                         "player_id": "p1", "time_limit_ms": 1000})

        self.assertEqual(store.priority_token, 9)
        self.assertEqual(store.state["priority_holder"], "p1")
        self.assertEqual(store.state["priority_token"], 9)
        self.assertEqual(seen[-1]["priority_holder"], "p1")
        self.assertEqual(seen[-1]["priority_token"], 9)

    def test_priority_grant_does_not_advance_the_state_seq(self):
        store = ClientStateStore()
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 5, "state": {}})
        self.assertEqual(store.last_server_seq, 5)

        store.apply_pdu({"type": "PRIORITY_GRANT", "seq_num": 9, "player_id": "p1"})

        self.assertEqual(store.last_server_seq, 5)


if __name__ == "__main__":
    unittest.main()
