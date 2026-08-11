import unittest

from client.gui import GameApplication
from client.gui_main import build_parser


class FakeRoot:
    @staticmethod
    def winfo_children():
        return []


class GuiMainTests(unittest.TestCase):
    def test_clear_root_does_not_depend_on_render_state(self):
        app = object.__new__(GameApplication)
        app.root = FakeRoot()
        app._strips = {"old": object()}
        app._card_widgets = {"old": object()}
        app.hand_tiles = {"old": object()}
        app.hand_buttons = {"old": object()}
        app._hand_positions = {"old": (1, 2)}
        app._hand_cards = {"old": object()}
        app._hovered_card_id = "old"

        app._clear_root()

        self.assertEqual(app._strips, {})
        self.assertEqual(app._hand_cards, {})
        self.assertIsNone(app._hovered_card_id)

    def test_connection_arguments_are_optional_and_keep_protocol_defaults(self):
        args = build_parser().parse_args([])

        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 4444)
        self.assertEqual(args.player_id, "")
        self.assertEqual(args.deck, "")

    def test_connection_arguments_prefill_the_desktop_form(self):
        args = build_parser().parse_args(
            ["--host", "game.local", "--port", "4555", "--id", "alice", "--deck", "decks/red.json"]
        )

        self.assertEqual((args.host, args.port, args.player_id, args.deck),
                         ("game.local", 4555, "alice", "decks/red.json"))


if __name__ == "__main__":
    unittest.main()
