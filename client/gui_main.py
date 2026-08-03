"""MTGNP desktop-client composition root."""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path

from client.gui import GameApplication
from client.gui_model import CardCatalog


ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MTGNP desktop client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4444)
    parser.add_argument("--id", default="", dest="player_id")
    parser.add_argument("--deck", default="")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Unable to start the desktop GUI: {exc}", file=sys.stderr)
        print("Repair or reinstall Python with the optional Tcl/Tk component enabled.", file=sys.stderr)
        return 1
    GameApplication(
        root,
        catalog=CardCatalog.from_path(ROOT / "cards.json"),
        asset_dir=ROOT / "client" / "assets" / "cards",
        host=args.host,
        port=args.port,
        player_id=args.player_id,
        deck_path=args.deck,
        verbose=args.verbose,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
