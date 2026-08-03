import threading
import time
import unittest

from client.controller import ClientController
from client.network_client import ClientNetwork
from client.state_store import ClientStateStore
from server.main import GameServer
from tests.helpers import BLUE_DECK, RED_DECK


def wait_for(predicate, message):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(0.01)
    raise AssertionError(message)


class EndToEndTests(unittest.TestCase):
    def test_two_real_clients_start_concede_and_restart_on_retained_connections(self):
        server = GameServer("127.0.0.1", 0, reconnect_timeout=0.2)
        server.start()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        clients = []
        try:
            stores, controllers, events = [], [], []
            for player_id in ("player_1", "player_2"):
                network = ClientNetwork(*server.address)
                store = ClientStateStore()
                observed = []
                network.subscribe(lambda pdu, s=store, o=observed: (o.append(pdu), s.apply_pdu(pdu)))
                network.connect()
                clients.append(network); stores.append(store); events.append(observed)
                controllers.append(ClientController(player_id, network, store))
            controllers[0].ready(RED_DECK); controllers[1].ready(BLUE_DECK)
            wait_for(lambda: all(s.state.get("lifecycle") == "MULLIGAN" for s in stores),
                     "both clients did not receive personalized mulligan state")
            previous_second_seq = stores[1].last_server_seq
            controllers[0].keep()
            wait_for(lambda: stores[1].last_server_seq != previous_second_seq,
                     "second client did not receive the first keep update")
            controllers[1].keep()
            wait_for(lambda: all(s.state.get("lifecycle") == "PLAYING" for s in stores),
                     f"game did not enter PLAYING; events={events}")
            controllers[0].concede()
            wait_for(lambda: any(p["type"] == "GAME_OVER" for p in events[1]),
                     "opponent did not receive GAME_OVER")
            game_over = next(p for p in events[1] if p["type"] == "GAME_OVER")
            self.assertEqual(game_over["reason"], "CONCEDE")
            controllers[0].ready(RED_DECK); controllers[1].ready(BLUE_DECK)
            wait_for(lambda: sum(p["type"] == "GAME_STATE_UPDATE" and
                                 p["state"].get("lifecycle") == "MULLIGAN"
                                 for p in events[0]) >= 2,
                     "retained clients could not start a fresh game")
        finally:
            for client in clients: client.close()
            server.stop(); thread.join(timeout=1)


if __name__ == "__main__":
    unittest.main()
