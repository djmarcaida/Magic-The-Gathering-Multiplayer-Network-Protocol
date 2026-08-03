import tkinter as tk
from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root_dir))

from client.gui import GameApplication
from client.gui_model import CardCatalog
from client.state_store import ClientStateStore


class FakeNetwork:
    def close(self):
        pass


class FakeController:
    pass


window = tk.Tk()
app = GameApplication(
    window,
    catalog=CardCatalog.from_path(root_dir / "cards.json"),
    asset_dir=root_dir / "client" / "assets" / "cards",
)
store = ClientStateStore()
app.attach_session("player_1", FakeController(), store, FakeNetwork())
store.apply_pdu({
    "type": "GAME_STATE_UPDATE",
    "seq_num": 17,
    "state": {
        "lifecycle": "PLAYING",
        "phase": "PRECOMBAT_MAIN",
        "turn": 4,
        "first_player": "player_1",
        "active_player": "player_1",
        "priority_holder": "player_1",
        "priority_token": 17,
        "life_totals": {"player_1": 20, "player_2": 18},
        "hand": {"player_1": ["mountain_003", "lightning_bolt_001", "goblin_guide_001", "shock_001"]},
        "hand_counts": {"player_1": 4, "player_2": 5},
        "library_counts": {"player_1": 33, "player_2": 35},
        "battlefield": {
            "player_1": [
                {"card_id": "mountain_001", "owner": "player_1", "controller": "player_1", "tapped": False, "summoning_sick": False, "damage": 0, "power_modifier": 0, "toughness_modifier": 0},
                {"card_id": "mountain_002", "owner": "player_1", "controller": "player_1", "tapped": True, "summoning_sick": False, "damage": 0, "power_modifier": 0, "toughness_modifier": 0},
                {"card_id": "monastery_swiftspear_001", "owner": "player_1", "controller": "player_1", "tapped": False, "summoning_sick": False, "damage": 0, "power_modifier": 0, "toughness_modifier": 0},
            ],
            "player_2": [
                {"card_id": "island_001", "owner": "player_2", "controller": "player_2", "tapped": True, "summoning_sick": False, "damage": 0, "power_modifier": 0, "toughness_modifier": 0},
                {"card_id": "ornithopter_001", "owner": "player_2", "controller": "player_2", "tapped": False, "summoning_sick": False, "damage": 0, "power_modifier": 0, "toughness_modifier": 0},
            ],
        },
        "graveyard": {"player_1": ["lava_spike_001"], "player_2": []},
        "exile": {"player_1": [], "player_2": []},
        "stack": [{"stack_item_id": "stk_1", "item_type": "SPELL", "source": "counterspell_001", "controller": "player_2", "targets": ["lightning_bolt_001"], "metadata": {}}],
        "combat": {"attackers": [], "blockers": {}, "damage_order": {}},
    },
})
if "--minimum" in sys.argv:
    window.geometry("1080x720")
window.after(250, window.lift)
window.after(300, window.focus_force)
window.mainloop()
