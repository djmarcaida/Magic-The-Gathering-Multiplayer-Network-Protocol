import tkinter as tk
import unittest
from pathlib import Path

from client.gui import GameApplication
from client.gui_model import CardCatalog
from client.state_store import ClientStateStore


ROOT = Path(__file__).resolve().parents[1]


class FakeController:
    def __init__(self):
        self.ready_decks = []

    def ready(self, deck):
        self.ready_decks.append(list(deck))
        return {"type": "PLAYER_READY"}


class FakeNetwork:
    def close(self):
        pass


class GuiSmokeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.update_idletasks()
            self.root.destroy()

    def test_game_screen_renders_authoritative_phase_and_hand(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        app = GameApplication(
            self.root,
            catalog=catalog,
            asset_dir=ROOT / "client" / "assets" / "cards",
        )
        app.attach_session("p1", FakeController(), store, FakeNetwork())

        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7, "state": self._state()})
        self.root.update_idletasks()

        self.assertEqual(app.phase_var.get(), "Pre-combat main")
        self.assertEqual(app.turn_var.get(), "Turn 1")
        self.assertEqual(app.priority_var.get(), "Your priority")
        self.assertEqual(len(app.hand_zone.winfo_children()), 2)

    def test_two_gui_interpreters_bind_card_images_to_their_own_window(self):
        second_root = tk.Tk()
        second_root.withdraw()
        try:
            catalog = CardCatalog.from_path(ROOT / "cards.json")
            first_store = ClientStateStore()
            second_store = ClientStateStore()
            first_app = GameApplication(self.root, catalog=catalog,
                                        asset_dir=ROOT / "client" / "assets" / "cards")
            second_app = GameApplication(second_root, catalog=catalog,
                                         asset_dir=ROOT / "client" / "assets" / "cards")
            first_app.attach_session("p1", FakeController(), first_store, FakeNetwork())
            second_app.attach_session("p1", FakeController(), second_store, FakeNetwork())

            first_store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7,
                                   "state": self._state()})
            second_store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7,
                                    "state": self._state()})

            self.assertEqual(len(first_app.hand_zone.winfo_children()), 2)
            self.assertEqual(len(second_app.hand_zone.winfo_children()), 2)
        finally:
            second_root.update_idletasks()
            second_root.destroy()

    def test_game_over_exposes_restart_with_original_deck(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        controller = FakeController()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", controller, store, FakeNetwork(),
                           deck_list=["mountain_001"])

        app._handle_event({"type": "GAME_OVER", "seq_num": 20,
                           "winner_id": "p2", "loser_id": "p1", "reason": "LIFE_ZERO"})
        app._ready_again()

        self.assertFalse(app.game_over)
        self.assertEqual(controller.ready_decks, [["mountain_001"]])

    @staticmethod
    def _state():
        return {
            "lifecycle": "PLAYING", "phase": "PRECOMBAT_MAIN", "turn": 1,
            "first_player": "p1", "active_player": "p1", "priority_holder": "p1",
            "priority_token": 7, "life_totals": {"p1": 20, "p2": 20},
            "hand": {"p1": ["mountain_001", "lightning_bolt_001"]},
            "hand_counts": {"p1": 2, "p2": 5}, "library_counts": {"p1": 41, "p2": 42},
            "battlefield": {"p1": [], "p2": []},
            "graveyard": {"p1": [], "p2": []}, "exile": {"p1": [], "p2": []},
            "stack": [], "combat": {"attackers": [], "blockers": {}, "damage_order": {}},
        }


if __name__ == "__main__":
    unittest.main()
