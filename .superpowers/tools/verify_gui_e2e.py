from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
from pathlib import Path

root_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))

from client.gui import GameApplication
from client.gui_model import CardCatalog
from server.main import GameServer


catalog = CardCatalog.from_path(root_dir / "cards.json")
assets = root_dir / "client" / "assets" / "cards"
server = GameServer("127.0.0.1", 0, reconnect_timeout=2)
server.start()
server_thread = threading.Thread(target=server.serve_forever, daemon=True)
server_thread.start()
port = server.address[1]

roots = [tk.Tk(), tk.Tk()]
apps = [
    GameApplication(roots[0], catalog=catalog, asset_dir=assets),
    GameApplication(roots[1], catalog=catalog, asset_dir=assets),
]
for app, player_id, deck in zip(apps, ("player_1", "player_2"),
                                (root_dir / "decks" / "red.json", root_dir / "decks" / "blue.json")):
    app.host_var.set("127.0.0.1")
    app.port_var.set(str(port))
    app.id_var.set(player_id)
    app.deck_var.set(str(deck))
    app._start_connection()


def pump_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for item in roots:
            item.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("GUI integration condition timed out")


try:
    pump_until(lambda: all(app.current_view and app.current_view.lifecycle == "MULLIGAN"
                           for app in apps))
    second_token = apps[1].store.last_server_seq
    apps[0]._send("keep")
    pump_until(lambda: apps[1].store.last_server_seq != second_token)
    apps[1]._send("keep")
    try:
        pump_until(lambda: all(app.current_view and app.current_view.lifecycle == "PLAYING"
                               for app in apps))
    except AssertionError:
        print("CLIENT_STATES", [(app.current_view.lifecycle, app.status_var.get(),
                                 app.store.last_server_seq) for app in apps])
        print("SERVER_STATE", server.engine.state.lifecycle,
              {pid: (player.kept, player.mulligans, len(player.hand))
               for pid, player in server.engine.state.players.items()})
        raise
    print(
        "GUI_E2E_OK",
        port,
        apps[0].current_view.player_id,
        apps[1].current_view.player_id,
        apps[0].current_view.phase,
    )
    apps[0]._send("concede")
    pump_until(lambda: all(app.game_over for app in apps))
    apps[0]._ready_again()
    pump_until(lambda: apps[0].current_view.lifecycle == "LOBBY")
    apps[1]._ready_again()
    pump_until(lambda: all(app.current_view and app.current_view.lifecycle == "MULLIGAN"
                           for app in apps))
    print("GUI_RESTART_OK", apps[0].current_view.lifecycle, apps[1].current_view.lifecycle)
finally:
    for app in apps:
        app.close()
    server.stop()
    server_thread.join(timeout=2)
