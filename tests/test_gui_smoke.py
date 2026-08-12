import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

from client.gui import HAND_REST_WIDTH, HAND_VIEWPORT_WIDTH, GameApplication
from client.gui_model import CardCatalog
from client.state_store import ClientStateStore


ROOT = Path(__file__).resolve().parents[1]


class FakeController:
    def __init__(self):
        self.ready_decks = []
        self.priority_passes = 0

    def ready(self, deck):
        self.ready_decks.append(list(deck))
        return {"type": "PLAYER_READY"}

    def pass_priority(self):
        self.priority_passes += 1
        return {"type": "PRIORITY_PASS"}


class FakeNetwork:
    def __init__(self):
        self.close_calls = 0

    def close(self):
        self.close_calls += 1


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
        self.assertEqual(app.turn_var.get(), "Turn 1 · Your turn")
        self.assertEqual(app.priority_var.get(), "Your priority")
        self.assertEqual(len(app.hand_zone.winfo_children()), 2)

        opponent_turn = self._state()
        opponent_turn["active_player"] = "p2"
        opponent_turn["priority_holder"] = "p2"
        opponent_turn["priority_token"] = None
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 8,
                         "state": opponent_turn})
        self.root.update_idletasks()

        self.assertEqual(app.turn_var.get(), "Turn 1 · Active: p2")
        self.assertEqual(app.priority_var.get(), "Priority: p2")

    def test_phase_strip_exposes_flow_arrows_and_neighboring_phases(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", FakeController(), store, FakeNetwork())

        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7,
                         "state": self._state()})
        self.root.update_idletasks()

        self.assertEqual(app.previous_phase_var.get(), "Draw")
        self.assertEqual(app.phase_var.get(), "Pre-combat main")
        self.assertEqual(app.next_phase_var.get(), "Begin combat")
        self.assertTrue(app.phase_before_arrow.find_all())
        self.assertTrue(app.phase_after_arrow.find_all())

    def test_passing_priority_immediately_hides_the_stale_holder_controls(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        controller = FakeController()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", controller, store, FakeNetwork())
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7,
                         "state": self._state()})
        self.root.update_idletasks()

        app._send("pass_priority", ())
        self.root.update_idletasks()

        self.assertEqual(controller.priority_passes, 1)
        self.assertEqual(app.priority_var.get(), "Passing priority...")
        self.assertNotIn(
            "Pass priority",
            [child.cget("text") for child in app.action_frame.winfo_children()
             if isinstance(child, ttk.Button)],
        )

        transferred = self._state()
        transferred["priority_holder"] = "p2"
        transferred["priority_token"] = None
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 8,
                         "state": transferred})
        self.root.update_idletasks()

        self.assertEqual(app.priority_var.get(), "Priority: p2")
        self.assertFalse(app._priority_pass_pending)

    def test_rejected_priority_pass_restores_the_holder_controls(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", FakeController(), store, FakeNetwork())
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7,
                         "state": self._state()})

        app._send("pass_priority", ())
        app._handle_error({"type": "ERROR", "code": "STALE_ACTION",
                           "message": "action rejected"})
        self.root.update_idletasks()

        self.assertEqual(app.priority_var.get(), "Your priority")
        self.assertFalse(app._priority_pass_pending)
        self.assertIn(
            "Pass priority",
            [child.cget("text") for child in app.action_frame.winfo_children()
             if isinstance(child, ttk.Button)],
        )

    def test_selected_hand_card_lifts_without_metadata_captions(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", FakeController(), store, FakeNetwork())
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7,
                         "state": self._state()})

        app._toggle_card("lightning_bolt_001")
        self.root.update_idletasks()

        focused = app.hand_tiles["lightning_bolt_001"]
        other = app.hand_tiles["mountain_001"]
        self.assertEqual(app._focused_card_id, "lightning_bolt_001")
        self.assertLess(focused.winfo_y(), other.winfo_y())
        self.assertGreater(
            app.hand_buttons["lightning_bolt_001"].winfo_reqwidth(),
            app.hand_buttons["mountain_001"].winfo_reqwidth(),
        )
        selected_button = app.hand_buttons["lightning_bolt_001"]
        self.assertEqual(selected_button._card_border_color.lower(), "#d76a5b")
        self.assertEqual(selected_button._card_emphasis, "selected")
        labels = [widget for widget in focused.winfo_children()
                  if isinstance(widget, tk.Label)]
        self.assertFalse(any(widget.cget("text").startswith("Mana:") for widget in labels))

        app._set_hand_hover("mountain_001", True)
        self.root.update_idletasks()

        self.assertIs(app.hand_zone.winfo_children()[-1], focused)
        self.assertEqual(selected_button._card_emphasis, "selected")

    def test_hand_hover_uses_larger_native_cards_and_scroll_only_viewport(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", FakeController(), store, FakeNetwork())
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7,
                         "state": self._state()})
        self.root.update_idletasks()

        button = app.hand_buttons["lightning_bolt_001"]
        resting_width = button.winfo_reqwidth()
        self.assertIsInstance(button, tk.Button)
        self.assertEqual(int(app.hand_viewport.cget("width")), HAND_VIEWPORT_WIDTH)
        self.assertGreaterEqual(resting_width, HAND_REST_WIDTH)

        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)

        control_labels = {
            str(widget.cget("text"))
            for widget in descendants(app.hand_viewport.master)
            if isinstance(widget, (tk.Button, ttk.Button, tk.Label, ttk.Label))
        }
        self.assertNotIn("Previous cards", control_labels)
        self.assertNotIn("Next cards", control_labels)
        self.assertFalse(any(isinstance(widget, ttk.Scrollbar)
                             for widget in descendants(app._shell)))
        self.assertFalse(hasattr(app, "_content_scrollbar"))

        app._set_hand_hover("lightning_bolt_001", True)
        self.root.update_idletasks()

        self.assertEqual(button._card_emphasis, "hover")
        self.assertGreater(button.winfo_reqwidth(), resting_width)

    def test_resource_strips_show_snapshot_counts_and_potential_mana(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", FakeController(), store, FakeNetwork())
        state = self._state()
        state["battlefield"]["p1"] = [{"id": "mountain_003", "tapped": False}]
        state["graveyard"]["p1"] = ["lightning_bolt_002"]
        state["exile"]["p2"] = ["island_003"]
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7, "state": state})
        self.root.update_idletasks()

        self.assertEqual(app.resource_life_var.get(), "20")
        self.assertEqual(app.resource_graveyard_var.get(), "1")
        self.assertEqual(app.opponent_resource_vars["exile"].get(), "1")
        self.assertEqual(app.resource_mana_var.get(), "Potential mana: R 1")

    def test_tapped_battlefield_card_rotates_and_keeps_selected_outline(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", FakeController(), store, FakeNetwork())
        state = self._state()
        state["battlefield"]["p1"] = [{"id": "mountain_003", "tapped": False}]
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 7, "state": state})
        app._toggle_card("mountain_003")
        self.root.update_idletasks()

        upright_outer = app._card_widgets["mountain_003"]
        upright_button = next(
            child for child in upright_outer.winfo_children() if isinstance(child, tk.Button))
        upright_image = upright_button._card_image
        self.assertEqual(upright_button._card_emphasis, "selected")
        self.assertEqual(upright_button._card_border_color.lower(), "#d76a5b")
        self.assertGreater(upright_image.height(), upright_image.width())

        tapped_state = self._state()
        tapped_state["battlefield"]["p1"] = [
            {"id": "mountain_003", "tapped": True}]
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 8,
                         "state": tapped_state})
        self.root.update_idletasks()

        tapped_outer = app._card_widgets["mountain_003"]
        tapped_button = next(
            child for child in tapped_outer.winfo_children() if isinstance(child, tk.Button))
        tapped_image = tapped_button._card_image
        self.assertEqual(tapped_button._card_emphasis, "selected")
        self.assertEqual(tapped_button._card_border_color.lower(), "#d76a5b")
        self.assertEqual(tapped_image.width(), upright_image.height())
        self.assertEqual(tapped_image.height(), upright_image.width())
        self.assertIn(
            "Tapped",
            [child.cget("text") for child in tapped_outer.winfo_children()
             if isinstance(child, tk.Label)],
        )

        untapped_state = self._state()
        untapped_state["battlefield"]["p1"] = [
            {"id": "mountain_003", "tapped": False}]
        store.apply_pdu({"type": "GAME_STATE_UPDATE", "seq_num": 9,
                         "state": untapped_state})
        self.root.update_idletasks()

        untapped_outer = app._card_widgets["mountain_003"]
        untapped_button = next(
            child for child in untapped_outer.winfo_children() if isinstance(child, tk.Button))
        self.assertEqual(untapped_button._card_image.width(), upright_image.width())
        self.assertEqual(untapped_button._card_image.height(), upright_image.height())

    def test_disconnect_recovery_closes_once_and_restores_prefilled_form(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        store = ClientStateStore()
        network = FakeNetwork()
        app = GameApplication(
            self.root, catalog=catalog,
            asset_dir=ROOT / "client" / "assets" / "cards",
            host="game.local", port=4555, player_id="p1", deck_path="decks/red.json",
        )
        app.attach_session("p1", FakeController(), store, network)

        app._connection_failed(ConnectionError("lost"), network)
        app._connection_failed(ConnectionError("lost again"), network)

        self.assertEqual(network.close_calls, 1)
        self.assertIsNone(app.controller)
        self.assertEqual(app.host_var.get(), "game.local")
        self.assertEqual(app.port_var.get(), "4555")
        self.assertEqual(app.id_var.get(), "p1")
        self.assertEqual(app.deck_var.get(), "decks/red.json")
        self.assertIn("try again", app.status_var.get())

    def test_activity_log_keeps_only_the_latest_250_messages(self):
        catalog = CardCatalog.from_path(ROOT / "cards.json")
        app = GameApplication(self.root, catalog=catalog,
                              asset_dir=ROOT / "client" / "assets" / "cards")
        app.attach_session("p1", FakeController(), ClientStateStore(), FakeNetwork())

        for value in range(255):
            app._append_log(f"event {value}")

        contents = app.activity_log.get("1.0", "end-1c")
        self.assertNotIn("event 4\n", contents)
        self.assertIn("event 5\n", f"{contents}\n")
        self.assertTrue(contents.endswith("event 254"))

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
            "hand": ["mountain_001", "lightning_bolt_001"],
            "hand_counts": {"p1": 2, "p2": 5}, "library_counts": {"p1": 41, "p2": 42},
            "battlefield": {"p1": [], "p2": []},
            "graveyard": {"p1": [], "p2": []}, "exile": {"p1": [], "p2": []},
            "stack": [], "combat": {"attackers": [], "blockers": {}, "damage_order": {}},
        }


if __name__ == "__main__":
    unittest.main()
