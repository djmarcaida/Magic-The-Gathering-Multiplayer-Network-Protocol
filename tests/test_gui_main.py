import unittest

from client.gui_main import build_parser


class GuiMainTests(unittest.TestCase):
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
