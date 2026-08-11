"""Tkinter presentation adapter for the MTGNP client layers.

DIRECTION CONTRACT
THESIS: A quiet tabletop control surface makes server authority and player choices obvious; it refuses both ornamental fantasy chrome and a redundant phase rail.
OWN-WORLD: Charcoal and felt surfaces, warm parchment headings, teal priority cues, color-semantic card outlines, and real card frames.
STORY: Connect, scan each player's resources at their battlefield, select a hand card, act through the protocol, and see the authoritative response.
FIRST VIEWPORT: Flowing phase strip above two battlefields and stack, fanned hand anchored below, contextual actions and history right.
FORM: Quiet Tabletop, fourth grounded direction, seed 1dc2138b.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
"""

from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from client.controller import ClientController
from client.gui_actions import build_blocker_mapping, dispatch_gui_action
from client.gui_model import (
    CardCatalog,
    CardView,
    GameView,
    GuiEventBridge,
    PHASE_LABELS,
    available_actions,
    bounded_activity_history,
    card_border_color,
    legal_target_options,
    phase_neighbors,
    resource_summary,
)
from client.main import load_deck
from client.network_client import ClientNetwork
from client.state_store import ClientStateStore


COLORS = {
    "background": "#101617",
    "surface": "#182021",
    "surface_raised": "#202a2b",
    "felt": "#24302f",
    "border": "#3a4847",
    "text": "#eee8dc",
    "muted": "#b8c1bd",
    "faint": "#899591",
    "accent": "#78c9be",
    "accent_dark": "#31554f",
    "warm": "#d8bd88",
    "danger": "#d99986",
    "mana_white": "#F3DF9B",
    "mana_blue": "#63A8D5",
    "mana_black": "#997AAF",
    "mana_red": "#D76A5B",
    "mana_green": "#63AA73",
    "mana_colorless": "#AFB5B1",
}

CARD_IMAGE_WIDTH = 144
ZONE_CARD_HEIGHT = 138
HAND_REST_WIDTH = CARD_IMAGE_WIDTH * 5 // 4
HAND_HOVER_WIDTH = 200
HAND_SELECTED_WIDTH = CARD_IMAGE_WIDTH * 3 // 2
HAND_STEP = 132
HAND_CARD_HEIGHT = 322
HAND_VISIBLE_COUNT = 4
HAND_VIEWPORT_WIDTH = HAND_STEP * (HAND_VISIBLE_COUNT - 1) + HAND_SELECTED_WIDTH + 16
HAND_SELECTED_Y = 4
HAND_HOVER_Y = 28
HAND_RESTING_Y = 62
HAND_ANIMATION_FRAMES = 6
HAND_ANIMATION_MS = 15
CARD_CORNER_RADIUS = 14
ACTIVITY_LOG_LIMIT = 250
BRIDGE_CALLBACK_LIMIT = 32


@dataclass
class CardStrip:
    canvas: tk.Canvas
    inner: tk.Frame
    window: int
    surface: str


class GameApplication:
    """Owns the desktop view while delegating transport and rules elsewhere."""

    def __init__(self, root: tk.Tk, *, catalog: CardCatalog, asset_dir: str | Path,
                 host: str = "127.0.0.1", port: int = 4444,
                 player_id: str = "", deck_path: str = "", verbose: bool = False):
        self.root = root
        self.catalog = catalog
        self.asset_dir = Path(asset_dir)
        self.verbose = verbose
        self.bridge = GuiEventBridge()
        self.network = None
        self.controller = None
        self.store = None
        self.player_id = player_id
        self.deck_list: list[str] = []
        self.game_over = False
        self.current_view: GameView | None = None
        self._selected: set[str] = set()
        self._focused_card_id: str | None = None
        self._card_widgets: dict[str, tk.Frame] = {}
        self.hand_tiles: dict[str, tk.Frame] = {}
        self.hand_buttons: dict[str, tk.Button] = {}
        self._hand_positions: dict[str, tuple[int, int]] = {}
        self._hand_cards: dict[str, CardView] = {}
        self._hand_animation_tokens: dict[str, int] = {}
        self._hovered_card_id: str | None = None
        self._strips: dict[tk.Frame, CardStrip] = {}
        self._images: dict[tuple[str, str], tk.PhotoImage] = {}
        self._outlined_images: dict[tuple[str, str, str], tk.PhotoImage] = {}
        self._tapped_images: dict[tuple[str, str, str], tk.PhotoImage] = {}
        self._closing = False
        self._game_screen_active = False
        self._priority_pass_pending = False
        self._connection_epoch = 0
        self._pending_network = None
        self._last_connection = (host, port, player_id, deck_path)
        self._displayed_phase: str | None = None
        self._displayed_turn: int | None = None
        self._displayed_lifecycle: str | None = None
        self._phase_animation_target: str | None = None
        self._phase_animation_token = 0
        self._activity_history: tuple[str, ...] = ()

        self.phase_var = tk.StringVar(value="Waiting for game state")
        self.turn_var = tk.StringVar(value="Turn —")
        self.priority_var = tk.StringVar(value="Not connected")
        self.status_var = tk.StringVar(value="Enter your connection details.")
        self.selection_var = tk.StringVar(value="No cards selected")
        self.previous_phase_var = tk.StringVar(value="")
        self.next_phase_var = tk.StringVar(value="")
        self.resource_life_var = tk.StringVar(value="--")
        self.resource_hand_var = tk.StringVar(value="--")
        self.resource_library_var = tk.StringVar(value="--")
        self.resource_graveyard_var = tk.StringVar(value="--")
        self.resource_exile_var = tk.StringVar(value="--")
        self.resource_land_var = tk.StringVar(value="--")
        self.resource_permanents_var = tk.StringVar(value="--")
        self.resource_mana_var = tk.StringVar(value="Potential mana: none")
        self.player_name_var = tk.StringVar(value="You")
        self.opponent_name_var = tk.StringVar(value="Opponent")
        self.opponent_resource_vars = {
            "life": tk.StringVar(value="--"), "hand": tk.StringVar(value="--"),
            "library": tk.StringVar(value="--"), "graveyard": tk.StringVar(value="--"),
            "exile": tk.StringVar(value="--"),
        }

        self.root.title("MTGNP — Quiet Tabletop")
        self.root.geometry("1400x900")
        self.root.minsize(1180, 860)
        self.root.configure(bg=COLORS["background"])
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_styles()
        self._show_connection(host, port, player_id, deck_path)
        self.root.after(40, self._drain_bridge)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLORS["background"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Raised.TFrame", background=COLORS["surface_raised"])
        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"],
                        font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=COLORS["muted"])
        style.configure("Title.TLabel", foreground=COLORS["warm"],
                        font=("Georgia", 23, "bold"))
        style.configure("Section.TLabel", foreground=COLORS["warm"],
                        font=("Georgia", 12, "bold"))
        style.configure("Status.TLabel", foreground=COLORS["accent"],
                        font=("Segoe UI Semibold", 10))
        style.configure("TEntry", fieldbackground="#f4f1e8", foreground="#182021", padding=8)
        style.configure("TButton", background="#303b3b", foreground=COLORS["text"],
                        borderwidth=0, padding=(12, 9), font=("Segoe UI Semibold", 9))
        style.map("TButton", background=[("active", "#3b4847"), ("disabled", "#252d2d")],
                  foreground=[("disabled", COLORS["faint"])])
        style.configure("Accent.TButton", background=COLORS["accent_dark"],
                        foreground="#f5fffd", padding=(14, 10))
        style.map("Accent.TButton", background=[("active", "#416f67")])
        style.configure("Danger.TButton", background="#5a3732", foreground="#ffe9e2")
        style.configure("Dark.Horizontal.TScrollbar", troughcolor=COLORS["surface"],
                        background=COLORS["border"], bordercolor=COLORS["surface"],
                        arrowcolor=COLORS["muted"], darkcolor=COLORS["border"],
                        lightcolor=COLORS["border"], relief="flat")
        style.configure("Dark.Vertical.TScrollbar", troughcolor=COLORS["surface"],
                        background=COLORS["border"], bordercolor=COLORS["surface"],
                        arrowcolor=COLORS["muted"], darkcolor=COLORS["border"],
                        lightcolor=COLORS["border"], relief="flat")

    def _clear_root(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self._strips.clear()
        self._card_widgets.clear()
        self.hand_tiles.clear()
        self.hand_buttons.clear()
        self._hand_positions.clear()
        self._hand_cards.clear()
        self._hovered_card_id = None

    @staticmethod
    def _close_networks(*networks) -> None:
        seen: set[int] = set()
        for network in networks:
            if network is None or id(network) in seen:
                continue
            seen.add(id(network))
            try:
                network.close()
            except OSError:
                pass

    def _show_connection(self, host: str, port: int, player_id: str, deck_path: str) -> None:
        self._game_screen_active = False
        self._clear_root()
        shell = ttk.Frame(self.root, padding=36)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        panel = tk.Frame(shell, bg=COLORS["surface"], highlightthickness=1,
                         highlightbackground=COLORS["border"], padx=34, pady=30)
        panel.grid(row=0, column=0)
        panel.columnconfigure(1, weight=1)

        ttk.Label(panel, text="MTGNP", style="Title.TLabel",
                  background=COLORS["surface"]).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(panel, text="Connect one player to the shared two-client match.",
                  style="Muted.TLabel", background=COLORS["surface"]).grid(
                      row=1, column=0, columnspan=3, sticky="w", pady=(4, 24))

        self.host_var = tk.StringVar(value=host)
        self.port_var = tk.StringVar(value=str(port))
        self.id_var = tk.StringVar(value=player_id)
        self.deck_var = tk.StringVar(value=deck_path)
        fields = (
            ("Server host", self.host_var),
            ("Server port", self.port_var),
            ("Player ID", self.id_var),
        )
        for row, (label, variable) in enumerate(fields, start=2):
            ttk.Label(panel, text=label, background=COLORS["surface"]).grid(
                row=row, column=0, sticky="w", padx=(0, 16), pady=7)
            ttk.Entry(panel, textvariable=variable, width=38).grid(
                row=row, column=1, columnspan=2, sticky="ew", pady=7)

        ttk.Label(panel, text="Deck file", background=COLORS["surface"]).grid(
            row=5, column=0, sticky="w", padx=(0, 16), pady=7)
        ttk.Entry(panel, textvariable=self.deck_var, width=38).grid(row=5, column=1, sticky="ew", pady=7)
        ttk.Button(panel, text="Browse", command=self._browse_deck).grid(row=5, column=2, padx=(8, 0), pady=7)

        ttk.Label(panel, textvariable=self.status_var, style="Status.TLabel",
                  background=COLORS["surface"], wraplength=470).grid(
                      row=6, column=0, columnspan=3, sticky="w", pady=(18, 12))
        self.connect_button = ttk.Button(panel, text="Connect to match", style="Accent.TButton",
                                         command=self._start_connection)
        self.connect_button.grid(row=7, column=0, columnspan=3, sticky="ew")

    def _browse_deck(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Choose a deck",
            filetypes=(("JSON deck", "*.json"), ("All files", "*.*")),
        )
        if path:
            self.deck_var.set(path)

    def _start_connection(self) -> None:
        try:
            host = self.host_var.get().strip()
            port = int(self.port_var.get().strip())
            player_id = self.id_var.get().strip()
            deck_path = self.deck_var.get().strip()
            if not host or not player_id or not deck_path:
                raise ValueError("Host, player ID, and deck file are required.")
            deck = load_deck(deck_path)
        except (OSError, ValueError) as exc:
            self.status_var.set(f"Cannot connect: {exc}")
            return

        self._last_connection = (host, port, player_id, deck_path)
        self._connection_epoch += 1
        epoch = self._connection_epoch
        self.connect_button.state(["disabled"])
        self.status_var.set("Connecting to the server…")
        network = ClientNetwork(host, port, verbose=self.verbose,
                                heartbeat_interval=5, heartbeat_timeout=15)
        self._pending_network = network
        store = ClientStateStore()
        controller = ClientController(player_id, network, store)
        network.subscribe(lambda pdu: self.bridge.post(store.apply_pdu, pdu))
        network.subscribe_disconnect(
            lambda exc, source=network: self.bridge.post(self._connection_failed, exc, source)
        )

        def connect_worker() -> None:
            try:
                network.connect()
            except (ConnectionError, OSError) as exc:
                self.bridge.post(self._connection_failed, exc, network)
                return
            self.bridge.post(self._finish_connection, epoch, player_id, deck, controller, store, network)

        threading.Thread(target=connect_worker, name="mtgnp-gui-connect", daemon=True).start()

    def _finish_connection(self, epoch: int, player_id: str, deck: list[str], controller,
                           store: ClientStateStore, network) -> None:
        if self._closing or epoch != self._connection_epoch:
            network.close()
            return
        self._pending_network = None
        self.attach_session(player_id, controller, store, network, deck_list=deck)
        try:
            controller.ready(deck)
            self._append_log("Connected. Deck submitted to the server.")
        except (ConnectionError, OSError) as exc:
            self._connection_failed(exc, network)

    def _connection_failed(self, exc: Exception, source=None) -> None:
        if self._closing:
            return
        if source is not None and source is not self._pending_network and source is not self.network:
            return
        message = f"Connection failed: {exc}. Check the server address and try again."
        self._connection_epoch += 1
        self._close_networks(self._pending_network, self.network)
        self._pending_network = None
        self.network = None
        self.controller = None
        self.store = None
        self.current_view = None
        self._priority_pass_pending = False
        self._selected.clear()
        self._focused_card_id = None
        self.priority_var.set("Disconnected")
        host, port, player_id, deck_path = self._last_connection
        if self._game_screen_active:
            self._show_connection(host, port, player_id, deck_path)
        self.status_var.set(message)
        if hasattr(self, "connect_button") and self.connect_button.winfo_exists():
            self.connect_button.state(["!disabled"])

    def attach_session(self, player_id: str, controller, store: ClientStateStore, network,
                       *, deck_list: list[str] | None = None) -> None:
        self.player_id = player_id
        self.controller = controller
        self.store = store
        self.network = network
        self._pending_network = None
        if deck_list is not None:
            self.deck_list = list(deck_list)
        store.subscribe_state(self._render_state)
        store.subscribe_event(self._handle_event)
        store.subscribe_error(self._handle_error)
        self._build_game_screen()

    def _build_game_screen(self) -> None:
        self._game_screen_active = True
        self._displayed_phase = None
        self._displayed_turn = None
        self._displayed_lifecycle = None
        self._phase_animation_target = None
        self._phase_animation_token += 1
        self._priority_pass_pending = False
        self._activity_history = ()
        self._clear_root()
        shell = ttk.Frame(self.root, padding=(12, 8, 12, 8))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=COLORS["surface"], highlightthickness=1,
                          highlightbackground=COLORS["border"], padx=16, pady=6)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(1, weight=1)
        brand = tk.Frame(header, bg=COLORS["surface"])
        brand.grid(row=0, column=0, sticky="w")
        ttk.Label(brand, text="MTGNP", style="Title.TLabel", background=COLORS["surface"]).pack(
            side="left")
        ttk.Label(brand, textvariable=self.turn_var, style="Muted.TLabel",
                  background=COLORS["surface"]).pack(side="left", padx=(12, 0), pady=(7, 0))
        self.phase_strip = tk.Frame(header, bg=COLORS["surface"], width=410, height=34)
        self.phase_strip.grid(row=0, column=1)
        self.phase_strip.grid_propagate(False)
        self.previous_phase_label = tk.Label(
            self.phase_strip, textvariable=self.previous_phase_var, bg=COLORS["surface"],
            fg=COLORS["faint"], font=("Segoe UI", 9), anchor="e")
        self.phase_current_label = tk.Label(
            self.phase_strip, textvariable=self.phase_var, bg=COLORS["surface"],
            fg=COLORS["warm"], font=("Georgia", 12, "bold"), anchor="center")
        self.phase_next_label = tk.Label(
            self.phase_strip, textvariable=self.next_phase_var, bg=COLORS["surface"],
            fg=COLORS["faint"], font=("Segoe UI", 9), anchor="w")
        self.phase_before_arrow = self._phase_arrow(self.phase_strip)
        self.phase_after_arrow = self._phase_arrow(self.phase_strip)
        self._place_phase_widgets()
        ttk.Label(header, textvariable=self.priority_var, style="Status.TLabel",
                  background=COLORS["surface"]).grid(row=0, column=2, sticky="e")

        content = tk.Frame(shell, bg=COLORS["background"])
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=0)
        content.rowconfigure(0, weight=1)
        self._shell = content

        board = tk.Frame(content, bg=COLORS["felt"], highlightthickness=1,
                         highlightbackground=COLORS["border"], padx=12, pady=6)
        board.grid(row=0, column=0, sticky="nsew")
        board.columnconfigure(0, weight=1)
        board.rowconfigure(1, weight=1)
        board.rowconfigure(4, weight=1)
        self._board = board

        self.opponent_resources = self._resource_strip(board, own=False)
        self.opponent_resources.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.opponent_zone = self._card_strip(board, 1)

        self.stack_zone = tk.Frame(board, bg=COLORS["surface"], highlightthickness=1,
                                   highlightbackground="#586765", padx=10, pady=8)
        self.stack_zone.grid(row=2, column=0, sticky="ew", pady=5)

        self.player_resources = self._resource_strip(board, own=True)
        self.player_resources.grid(row=3, column=0, sticky="ew", pady=(5, 4))
        self.player_zone = self._card_strip(board, 4)

        hand_panel = tk.Frame(board, bg=COLORS["surface"], highlightthickness=1,
                              highlightbackground="#655b43", padx=8, pady=4)
        hand_panel.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        hand_panel.columnconfigure(0, weight=1)
        hand_header = tk.Frame(hand_panel, bg=COLORS["surface"])
        hand_header.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        hand_header.columnconfigure(0, weight=1)
        ttk.Label(hand_header, text="Your hand", style="Section.TLabel",
                  background=COLORS["surface"]).grid(row=0, column=0, sticky="w")

        hand_viewport = tk.Frame(
            hand_panel, bg=COLORS["surface"], width=HAND_VIEWPORT_WIDTH,
            height=HAND_CARD_HEIGHT)
        self.hand_viewport = hand_viewport
        hand_viewport.grid(row=1, column=0)
        hand_viewport.grid_propagate(False)
        hand_viewport.columnconfigure(0, weight=1)
        hand_viewport.rowconfigure(0, weight=1)
        self.hand_zone = self._card_strip(hand_viewport, 0, surface=COLORS["surface"])
        hand_strip = self._strips[self.hand_zone]
        hand_strip.canvas.configure(
            height=HAND_CARD_HEIGHT, width=HAND_VIEWPORT_WIDTH,
            xscrollincrement=HAND_STEP)
        hand_strip.canvas.bind("<MouseWheel>", self._on_hand_mousewheel)

        side = tk.Frame(content, bg=COLORS["surface"], highlightthickness=1,
                        highlightbackground=COLORS["border"], padx=12, pady=12, width=285)
        side.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(5, weight=1)
        ttk.Label(side, text="Available actions", style="Section.TLabel",
                  background=COLORS["surface"]).grid(row=0, column=0, sticky="w")
        ttk.Label(side, textvariable=self.selection_var, style="Muted.TLabel",
                  background=COLORS["surface"], wraplength=250).grid(
                      row=1, column=0, sticky="ew", pady=(4, 9))
        self.action_frame = tk.Frame(side, bg=COLORS["surface"])
        self.action_frame.grid(row=2, column=0, sticky="ew")
        ttk.Separator(side).grid(row=3, column=0, sticky="ew", pady=12)
        ttk.Label(side, text="Activity", style="Section.TLabel",
                  background=COLORS["surface"]).grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.activity_log = tk.Text(side, height=12, width=31, wrap="word", state="disabled",
                                    bg="#121819", fg=COLORS["muted"], insertbackground=COLORS["text"],
                                    selectbackground=COLORS["accent_dark"], relief="flat",
                                    font=("Segoe UI", 9), padx=8, pady=8)
        self.activity_log.grid(row=5, column=0, sticky="nsew")
        self._activity_empty = True
        self._set_activity_empty_state()
        ttk.Button(side, text="Concede match", style="Danger.TButton",
                   command=self._confirm_concede).grid(row=6, column=0, sticky="ew", pady=(10, 0))
        self._side = side

        footer = ttk.Label(content, textvariable=self.status_var, style="Muted.TLabel")
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self._footer = footer
        self.status_var.set("Connected. Waiting for the server's game state.")

    def _resource_strip(self, parent: tk.Misc, *, own: bool) -> tk.Frame:
        strip = tk.Frame(parent, bg=COLORS["felt"])
        identity = tk.Frame(strip, bg=COLORS["felt"])
        identity.grid(row=0, column=0, rowspan=2 if own else 1, sticky="nw",
                      padx=(0, 16), pady=(1, 0))
        tk.Label(identity, textvariable=self.player_name_var if own else self.opponent_name_var,
                 bg=COLORS["felt"], fg=COLORS["warm"],
                 font=("Georgia", 12, "bold")).pack(anchor="w")
        tk.Label(identity, text="Battlefield", bg=COLORS["felt"], fg=COLORS["faint"],
                 font=("Segoe UI", 8)).pack(anchor="w")
        metrics_frame = tk.Frame(strip, bg=COLORS["felt"])
        metrics_frame.grid(row=0, column=1, sticky="w")
        if own:
            metrics = (
                ("life", "Life", self.resource_life_var),
                ("hand", "Hand", self.resource_hand_var),
                ("library", "Library", self.resource_library_var),
                ("graveyard", "Graveyard", self.resource_graveyard_var),
                ("exile", "Exile", self.resource_exile_var),
                ("land", "Land", self.resource_land_var),
                ("permanent", "Permanents", self.resource_permanents_var),
            )
        else:
            metrics = (
                ("life", "Life", self.opponent_resource_vars["life"]),
                ("hand", "Hand", self.opponent_resource_vars["hand"]),
                ("library", "Library", self.opponent_resource_vars["library"]),
                ("graveyard", "Graveyard", self.opponent_resource_vars["graveyard"]),
                ("exile", "Exile", self.opponent_resource_vars["exile"]),
            )
        columns = 8 if own else 5
        for index, (icon, label, variable) in enumerate(metrics):
            self._resource_metric(metrics_frame, icon, label, variable).grid(
                row=index // columns, column=index % columns, sticky="w",
                padx=(0, 10), pady=1)
        if own:
            mana_index = len(metrics)
            mana = tk.Frame(metrics_frame, bg=COLORS["felt"])
            mana.grid(row=mana_index // columns, column=mana_index % columns,
                      sticky="w", padx=(0, 10), pady=1)
            tk.Label(mana, text="Potential mana", bg=COLORS["felt"],
                     fg=COLORS["faint"], font=("Segoe UI", 8)).pack(side="left")
            self.mana_pips_frame = tk.Frame(mana, bg=COLORS["felt"])
            self.mana_pips_frame.pack(side="left", padx=(5, 0))
        return strip

    def _resource_metric(self, parent: tk.Misc, icon: str, label: str,
                         variable: tk.StringVar) -> tk.Frame:
        metric = tk.Frame(parent, bg=COLORS["felt"])
        canvas = tk.Canvas(metric, width=13, height=13, bg=COLORS["felt"],
                           highlightthickness=0)
        canvas.pack(side="left", padx=(0, 3))
        self._draw_resource_icon(canvas, icon)
        tk.Label(metric, text=label, bg=COLORS["felt"], fg=COLORS["faint"],
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Label(metric, textvariable=variable, bg=COLORS["felt"], fg=COLORS["text"],
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(2, 0))
        return metric

    @staticmethod
    def _draw_resource_icon(canvas: tk.Canvas, icon: str) -> None:
        color = COLORS["accent"]
        if icon == "life":
            canvas.create_oval(2, 2, 8, 8, outline=color, fill=color)
            canvas.create_oval(5, 2, 11, 8, outline=color, fill=color)
            canvas.create_polygon(2, 5, 11, 5, 6.5, 11, fill=color, outline=color)
        elif icon == "hand":
            canvas.create_rectangle(2, 2, 9, 11, outline=color, width=1)
            canvas.create_line(4, 1, 11, 8, fill=color, width=1)
        elif icon == "library":
            canvas.create_rectangle(2, 2, 10, 11, outline=color, width=1)
            canvas.create_line(4, 5, 8, 5, fill=color)
            canvas.create_line(4, 8, 8, 8, fill=color)
        elif icon == "graveyard":
            canvas.create_line(2, 10, 11, 10, fill=color, width=1)
            canvas.create_line(6, 2, 6, 10, fill=color, width=2)
            canvas.create_line(3, 5, 9, 5, fill=color, width=2)
        elif icon == "exile":
            canvas.create_polygon(6.5, 1, 11, 6.5, 6.5, 12, 2, 6.5, outline=color, fill="")
        elif icon == "land":
            canvas.create_rectangle(2, 3, 11, 10, outline=color, width=1)
            canvas.create_line(4, 8, 7, 5, 10, 8, fill=color, width=1)
        else:
            canvas.create_rectangle(2, 2, 11, 11, outline=color, width=1)
            canvas.create_line(4, 4, 9, 9, fill=color)
            canvas.create_line(9, 4, 4, 9, fill=color)

    @staticmethod
    def _phase_arrow(parent: tk.Misc) -> tk.Canvas:
        canvas = tk.Canvas(parent, width=18, height=22, bg=COLORS["surface"],
                           highlightthickness=0)
        canvas.create_line(2, 11, 15, 11, fill=COLORS["accent"], width=2,
                           arrow="last", arrowshape=(6, 7, 3))
        return canvas

    def _card_strip(self, parent, row: int, *, surface: str | None = None) -> tk.Frame:
        surface = surface or COLORS["felt"]
        container = tk.Frame(parent, bg=surface)
        container.grid(row=row, column=0, sticky="nsew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        canvas = tk.Canvas(container, bg=surface, highlightthickness=0,
                           height=ZONE_CARD_HEIGHT)
        canvas.grid(row=0, column=0, sticky="nsew")
        inner = tk.Frame(canvas, bg=surface)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def refresh_scrollregion() -> None:
            bbox = canvas.bbox("all")
            canvas.configure(scrollregion=bbox)

        def inner_changed(_event) -> None:
            refresh_scrollregion()

        def canvas_changed(event) -> None:
            if getattr(inner, "_layout_mode", "flow") != "fanned":
                canvas.itemconfigure(window, height=max(event.height, inner.winfo_reqheight()))
            refresh_scrollregion()

        inner.bind("<Configure>", inner_changed)
        canvas.bind("<Configure>", canvas_changed)
        canvas.bind("<MouseWheel>", lambda event: self._scroll_card_canvas(canvas, event))
        canvas.bind("<Shift-MouseWheel>", lambda event: self._scroll_card_canvas(canvas, event))
        self._strips[inner] = CardStrip(canvas, inner, window, surface)
        return inner

    @staticmethod
    def _clear_frame(frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _place_phase_widgets(self, shift: int = 0) -> None:
        self.previous_phase_label.place(x=-shift, y=6, width=112, height=22)
        self.phase_before_arrow.place(x=115-shift, y=5, width=18, height=22)
        self.phase_current_label.place(x=136-shift, y=3, width=138, height=26)
        self.phase_after_arrow.place(x=277-shift, y=5, width=18, height=22)
        self.phase_next_label.place(x=298-shift, y=6, width=112, height=22)

    def _set_phase_labels(self, phase: str) -> None:
        previous, current, following = phase_neighbors(phase)
        self.previous_phase_var.set(PHASE_LABELS.get(previous, previous.replace("_", " ").title()))
        self.phase_var.set(PHASE_LABELS.get(current, current.replace("_", " ").title()))
        self.next_phase_var.set(PHASE_LABELS.get(following, following.replace("_", " ").title()))
        self._place_phase_widgets()

    def _render_phase_strip(self, phase: str, *, turn: int, lifecycle: str) -> None:
        displayed = self._displayed_phase
        displayed_turn = self._displayed_turn
        displayed_lifecycle = self._displayed_lifecycle
        phases = tuple(PHASE_LABELS)
        try:
            previous_index = phases.index(displayed) if displayed is not None else -1
            current_index = phases.index(phase)
        except ValueError:
            previous_index = current_index = -1
        consecutive = (
            displayed_lifecycle == lifecycle == "PLAYING"
            and (
                (current_index == previous_index + 1 and turn == displayed_turn)
                or (previous_index == len(phases) - 1 and current_index == 0
                    and displayed_turn is not None and turn == displayed_turn + 1)
            )
        )

        self._displayed_phase = phase
        self._displayed_turn = turn
        self._displayed_lifecycle = lifecycle
        self._phase_animation_token += 1
        token = self._phase_animation_token
        self._phase_animation_target = None
        if displayed is None or displayed == phase or not consecutive:
            self._set_phase_labels(phase)
            return

        self._phase_animation_target = phase

        def animate(frame: int = 1) -> None:
            if token != self._phase_animation_token or not self._game_screen_active:
                return
            self._place_phase_widgets(round(136 * frame / 10))
            if frame < 10:
                self.root.after(15, animate, frame + 1)
            else:
                self._set_phase_labels(phase)
                self._phase_animation_target = None

        animate()

    def _render_state(self, state: dict[str, object]) -> None:
        if not self._game_screen_active:
            return
        try:
            view = GameView.from_state(self.player_id, state, self.catalog)
        except (KeyError, TypeError, ValueError) as exc:
            self.status_var.set(f"Cannot display the latest state: {exc}")
            return
        self.current_view = view
        if not view.has_priority:
            self._priority_pass_pending = False
        if view.lifecycle in {"MULLIGAN", "PLAYING"}:
            self.game_over = False
        visible_ids = {
            card.instance_id for card in (*view.hand, *view.player.battlefield,
                                          *view.opponent.battlefield)
        }
        self._selected.intersection_update(visible_ids)
        hand_ids = {card.instance_id for card in view.hand}
        if self._focused_card_id not in hand_ids:
            self._focused_card_id = None
        self.selection_var.set(
            ", ".join(self._card_label(item) for item in sorted(self._selected))
            if self._selected else "No cards selected"
        )
        turn_owner = "Your turn" if view.is_active_player else f"Active: {view.active_player}"
        self.turn_var.set(f"Turn {view.turn} · {turn_owner}")
        self._render_phase_strip(view.phase, turn=view.turn, lifecycle=view.lifecycle)
        if self._priority_pass_pending and view.has_priority:
            self.priority_var.set("Passing priority...")
        elif view.has_priority:
            self.priority_var.set("Your priority")
        elif view.priority_holder:
            self.priority_var.set(f"Priority: {view.priority_holder}")
        else:
            self.priority_var.set("Resolving state")
        self._render_resources(view)
        self._card_widgets.clear()
        self._render_cards(self.opponent_zone, view.opponent.battlefield)
        self._render_cards(self.player_zone, view.player.battlefield)
        self._render_hand(view.hand)
        self._render_stack(view)
        self._render_actions(view)
        self.status_var.set("State synchronized with the server.")

    def _render_resources(self, view: GameView) -> None:
        player = resource_summary(view.player)
        opponent = resource_summary(view.opponent)
        self.player_name_var.set("You")
        self.opponent_name_var.set(view.opponent.player_id)
        self.resource_life_var.set(str(player.life))
        self.resource_hand_var.set(str(player.hand_count))
        self.resource_library_var.set(str(player.library_count))
        self.resource_graveyard_var.set(str(player.graveyard_count))
        self.resource_exile_var.set(str(player.exile_count))
        self.resource_land_var.set("played" if player.land_played else "available")
        self.resource_permanents_var.set(str(player.permanent_count))
        for key, value in (
            ("life", opponent.life), ("hand", opponent.hand_count),
            ("library", opponent.library_count), ("graveyard", opponent.graveyard_count),
            ("exile", opponent.exile_count),
        ):
            self.opponent_resource_vars[key].set(str(value))

        mana_text = " ".join(f"{color} {player.mana_sources[color]}" for color in "WUBRGC"
                             if color in player.mana_sources)
        self.resource_mana_var.set(f"Potential mana: {mana_text or 'none'}")
        self._clear_frame(self.mana_pips_frame)
        pip_colors = {
            "W": COLORS["mana_white"], "U": COLORS["mana_blue"], "B": COLORS["mana_black"],
            "R": COLORS["mana_red"], "G": COLORS["mana_green"], "C": COLORS["mana_colorless"],
        }
        for color in "WUBRGC":
            amount = player.mana_sources.get(color, 0)
            if amount:
                tk.Label(self.mana_pips_frame, text=f"{color}×{amount}", bg=pip_colors[color],
                         fg=COLORS["background"], font=("Segoe UI", 8, "bold"), padx=4, pady=1).pack(
                             side="left", padx=(0, 3))
        if not player.mana_sources:
            tk.Label(self.mana_pips_frame, text="none", bg=COLORS["felt"],
                     fg=COLORS["muted"], font=("Segoe UI", 8)).pack(side="left")

    def _render_cards(self, frame: tk.Frame, cards: tuple[CardView, ...]) -> None:
        self._clear_frame(frame)
        if not cards:
            tk.Label(frame, text="No cards in this zone", bg=frame.cget("bg"),
                     fg=COLORS["faint"], font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=16)
            return
        for card in cards:
            selected = card.instance_id in self._selected
            border_color = card_border_color(card)
            surface = frame.cget("bg")
            outer = tk.Frame(frame, bg=surface)
            outer.pack(side="left", padx=(0, 8), pady=2)
            emphasis = "selected" if selected else "rest"
            image = self._battlefield_card_image(card, "small", emphasis)
            button = tk.Button(
                outer,
                image=image,
                text=card.name,
                command=lambda card_id=card.instance_id: self._toggle_card(card_id),
                bg=surface, fg=COLORS["text"], activebackground=surface,
                activeforeground=COLORS["text"], relief="flat", bd=0,
                padx=0, pady=0,
                width=18 if image is None else 0, height=12 if image is None else 0,
                cursor="hand2", highlightthickness=0,
                takefocus=True,
            )
            button.pack()
            button._card_image = image
            button._card_border_color = border_color
            button._card_emphasis = emphasis
            button.bind("<Return>", lambda _event, card_id=card.instance_id: self._toggle_card(card_id))
            button.bind("<space>", lambda _event, card_id=card.instance_id: self._toggle_card(card_id))
            button.bind(
                "<MouseWheel>",
                lambda event, canvas=self._strips[frame].canvas:
                    self._scroll_card_canvas(canvas, event),
            )

            status = []
            if card.tapped:
                status.append("Tapped")
            if card.damage:
                status.append(f"{card.damage} damage")
            if card.summoning_sick:
                status.append("Summoning sick")
            if status:
                tk.Label(outer, text=" · ".join(status), bg=surface,
                         fg=COLORS["danger"], font=("Segoe UI Semibold", 8), anchor="w").pack(
                             fill="x", padx=3, pady=(2, 3))
            self._card_widgets[card.instance_id] = outer

    def _render_hand(self, cards: tuple[CardView, ...]) -> None:
        strip = self._strips[self.hand_zone]
        self._clear_frame(self.hand_zone)
        self.hand_tiles.clear()
        self.hand_buttons.clear()
        self._hand_positions.clear()
        self._hand_cards = {card.instance_id: card for card in cards}
        if self._hovered_card_id not in self._hand_cards:
            self._hovered_card_id = None
        self.hand_zone._layout_mode = "fanned"
        if not cards:
            tk.Label(self.hand_zone, text="No cards in hand", bg=strip.surface,
                     fg=COLORS["faint"], font=("Segoe UI", 9)).place(x=8, y=72)
            strip.canvas.itemconfigure(strip.window, width=max(220, strip.canvas.winfo_width()),
                                       height=HAND_CARD_HEIGHT)
            strip.canvas.configure(scrollregion=strip.canvas.bbox("all"))
            return

        card_width = HAND_SELECTED_WIDTH + 12
        total_width = max(strip.canvas.winfo_width(), HAND_STEP * (len(cards) - 1) + card_width + 8)
        strip.canvas.itemconfigure(strip.window, width=total_width, height=HAND_CARD_HEIGHT)
        focused_button = None
        for index, card in enumerate(cards):
            selected = card.instance_id in self._selected
            focused = card.instance_id == self._focused_card_id
            hovered = card.instance_id == self._hovered_card_id and not selected
            emphasis = "selected" if selected else "hover" if hovered else "rest"
            size = "hand_selected" if selected else "hand_hover" if hovered else "hand_rest"
            outer = tk.Frame(self.hand_zone, bg=strip.surface)
            image = self._outlined_card_image(card, size, emphasis)
            button = tk.Button(
                outer, image=image, text=card.name,
                command=lambda card_id=card.instance_id: self._toggle_card(card_id),
                bg=strip.surface, fg=COLORS["text"], activebackground=strip.surface,
                activeforeground=COLORS["text"], relief="flat", bd=0,
                padx=0, pady=0,
                width=18 if image is None else 0, height=12 if image is None else 0,
                cursor="hand2", highlightthickness=0,
                takefocus=True,
            )
            button.pack()
            button._card_image = image
            button._card_border_color = card_border_color(card)
            button._card_emphasis = emphasis
            button.bind("<Return>", lambda _event, card_id=card.instance_id: self._toggle_card(card_id))
            button.bind("<space>", lambda _event, card_id=card.instance_id: self._toggle_card(card_id))
            button.bind(
                "<Enter>", lambda _event, card_id=card.instance_id: self._set_hand_hover(card_id, True))
            button.bind(
                "<Leave>", lambda _event, card_id=card.instance_id: self._set_hand_hover(card_id, False))
            button.bind("<MouseWheel>", self._on_hand_mousewheel)
            x = index * HAND_STEP
            y = HAND_SELECTED_Y if selected else HAND_HOVER_Y if hovered else HAND_RESTING_Y
            outer.place(x=x, y=y)
            self.hand_tiles[card.instance_id] = outer
            self.hand_buttons[card.instance_id] = button
            self._card_widgets[card.instance_id] = outer
            self._hand_positions[card.instance_id] = (x, card_width)
            if focused:
                focused_button = button
        self._raise_selected_hand_cards()
        if focused_button is not None:
            focused_button.focus_set()
        strip.canvas.configure(scrollregion=strip.canvas.bbox("all"))
        if self._focused_card_id:
            self.root.after_idle(self._keep_focused_hand_card_visible)

    def _card_image(self, base_id: str, size: str) -> tk.PhotoImage | None:
        key = (base_id, size)
        if key in self._images:
            return self._images[key]
        path = self.asset_dir / f"{base_id}.png"
        if not path.exists():
            return None
        try:
            image = tk.PhotoImage(master=self.root, file=str(path))
            if size == "small":
                image = image.zoom(3, 3).subsample(8, 8)
            elif size == "hand_rest":
                image = image.zoom(3, 3).subsample(4, 4)
            elif size == "hand_hover":
                image = image.zoom(5, 5).subsample(6, 6)
            elif size == "hand_selected":
                image = image.zoom(9, 9).subsample(10, 10)
        except tk.TclError:
            return None
        self._images[key] = image
        return image

    def _outlined_card_image(self, card: CardView, size: str,
                             emphasis: str) -> tk.PhotoImage | None:
        key = (card.base_id, size, emphasis)
        if key in self._outlined_images:
            return self._outlined_images[key]
        source = self._card_image(card.base_id, size)
        if source is None:
            return None
        border = {"rest": 2, "hover": 4, "selected": 6}[emphasis]
        width = source.width() + border * 2
        height = source.height() + border * 2
        radius = CARD_CORNER_RADIUS + border
        try:
            image = tk.PhotoImage(master=self.root, width=width, height=height)
            image.put(card_border_color(card), to=(0, 0, width, height))
            for y in range(radius):
                for x in range(radius):
                    if (x - radius) ** 2 + (y - radius) ** 2 <= radius ** 2:
                        continue
                    for corner_x, corner_y in (
                        (x, y), (width - 1 - x, y),
                        (x, height - 1 - y), (width - 1 - x, height - 1 - y),
                    ):
                        image.transparency_set(corner_x, corner_y, True)
            image.tk.call(str(image), "copy", str(source), "-to", border, border)
        except (AttributeError, tk.TclError):
            image = source
        self._outlined_images[key] = image
        return image

    def _battlefield_card_image(self, card: CardView, size: str,
                                emphasis: str) -> tk.PhotoImage | None:
        image = self._outlined_card_image(card, size, emphasis)
        if image is None or not card.tapped:
            return image

        key = (card.base_id, size, emphasis)
        if key in self._tapped_images:
            return self._tapped_images[key]

        try:
            rotated = tk.PhotoImage(
                master=self.root, width=image.height(), height=image.width())
            for destination_y in range(image.width()):
                colors = []
                transparent_pixels = []
                for destination_x in range(image.height()):
                    source_x = destination_y
                    source_y = image.height() - 1 - destination_x
                    color = image.get(source_x, source_y)
                    if isinstance(color, tuple):
                        color = "#{:02x}{:02x}{:02x}".format(*color[:3])
                    colors.append(color)
                    if image.transparency_get(source_x, source_y):
                        transparent_pixels.append(destination_x)
                rotated.put("{" + " ".join(colors) + "}", to=(0, destination_y))
                for destination_x in transparent_pixels:
                    rotated.transparency_set(destination_x, destination_y, True)
        except (AttributeError, tk.TclError):
            rotated = image

        self._tapped_images[key] = rotated
        return rotated

    def _set_hand_hover(self, card_id: str, entering: bool) -> None:
        if card_id not in self._hand_cards or card_id in self._selected:
            return
        if entering:
            previous = self._hovered_card_id
            self._hovered_card_id = card_id
            if previous and previous != card_id and previous not in self._selected:
                self._apply_hand_card_visual(previous, "rest", HAND_RESTING_Y)
            self._apply_hand_card_visual(card_id, "hover", HAND_HOVER_Y)
        elif self._hovered_card_id == card_id:
            self._hovered_card_id = None
            self._apply_hand_card_visual(card_id, "rest", HAND_RESTING_Y)

    def _apply_hand_card_visual(self, card_id: str, emphasis: str, target_y: int) -> None:
        card = self._hand_cards.get(card_id)
        button = self.hand_buttons.get(card_id)
        tile = self.hand_tiles.get(card_id)
        if card is None or button is None or tile is None:
            return
        try:
            if not tile.winfo_exists():
                return
        except tk.TclError:
            return
        size = {
            "rest": "hand_rest", "hover": "hand_hover", "selected": "hand_selected"
        }[emphasis]
        image = self._outlined_card_image(card, size, emphasis)
        button.configure(image=image)
        button._card_image = image
        button._card_emphasis = emphasis
        tile.lift()
        self._raise_selected_hand_cards()
        self._animate_hand_card(card_id, target_y)

    def _raise_selected_hand_cards(self) -> None:
        """Keep persistent selection above temporary neighboring hover previews."""
        for card_id in self._hand_cards:
            if card_id in self._selected and card_id != self._focused_card_id:
                tile = self.hand_tiles.get(card_id)
                if tile is not None:
                    tile.lift()
        focused = self.hand_tiles.get(self._focused_card_id)
        if focused is not None and self._focused_card_id in self._selected:
            focused.lift()

    def _animate_hand_card(self, card_id: str, target_y: int) -> None:
        tile = self.hand_tiles.get(card_id)
        if tile is None:
            return
        token = self._hand_animation_tokens.get(card_id, 0) + 1
        self._hand_animation_tokens[card_id] = token
        try:
            start_y = tile.winfo_y()
        except tk.TclError:
            return

        def step(frame: int = 1) -> None:
            try:
                if self._hand_animation_tokens.get(card_id) != token or not tile.winfo_exists():
                    return
                progress = 1 - (1 - frame / HAND_ANIMATION_FRAMES) ** 3
                tile.place_configure(y=round(start_y + (target_y - start_y) * progress))
            except tk.TclError:
                return
            if frame < HAND_ANIMATION_FRAMES:
                self.root.after(HAND_ANIMATION_MS, step, frame + 1)

        step()

    def _scroll_hand(self, direction: int) -> None:
        if hasattr(self, "hand_zone"):
            self._strips[self.hand_zone].canvas.xview_scroll(direction, "units")

    @staticmethod
    def _scroll_card_canvas(canvas: tk.Canvas, event: tk.Event) -> str:
        if event.delta:
            canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _on_hand_mousewheel(self, event: tk.Event) -> str:
        return self._scroll_card_canvas(self._strips[self.hand_zone].canvas, event)

    def _toggle_card(self, card_id: str) -> None:
        if card_id in self._selected:
            self._selected.remove(card_id)
        else:
            self._selected.add(card_id)
        if self.current_view is not None:
            hand_ids = {card.instance_id for card in self.current_view.hand}
            if card_id in self._selected and card_id in hand_ids:
                self._focused_card_id = card_id
            elif card_id == self._focused_card_id:
                self._focused_card_id = next((item.instance_id for item in self.current_view.hand
                                               if item.instance_id in self._selected), None)
        self.selection_var.set(
            ", ".join(self._card_label(item) for item in sorted(self._selected))
            if self._selected else "No cards selected"
        )
        if self.current_view is not None:
            self._card_widgets.clear()
            self._render_cards(self.opponent_zone, self.current_view.opponent.battlefield)
            self._render_cards(self.player_zone, self.current_view.player.battlefield)
            self._render_hand(self.current_view.hand)
            self._render_actions(self.current_view)

    def _keep_focused_hand_card_visible(self) -> None:
        if self._focused_card_id is None or self._focused_card_id not in self._hand_positions:
            return
        strip = self._strips[self.hand_zone]
        bbox = strip.canvas.bbox("all")
        if bbox is None:
            return
        content_width = max(1, bbox[2] - bbox[0])
        left, width = self._hand_positions[self._focused_card_id]
        viewport = strip.canvas.winfo_width()
        first, last = strip.canvas.xview()
        visible_left = first * content_width
        visible_right = last * content_width
        if left < visible_left:
            strip.canvas.xview_moveto(max(0, left / content_width))
        elif left + width > visible_right:
            strip.canvas.xview_moveto(min(1, max(0, (left + width - viewport) / content_width)))

    def _render_stack(self, view: GameView) -> None:
        self._clear_frame(self.stack_zone)
        ttk.Label(self.stack_zone, text="Stack", style="Section.TLabel",
                  background=COLORS["surface"]).pack(side="left", padx=(0, 14))
        if not view.stack:
            ttk.Label(self.stack_zone, text="Empty", style="Muted.TLabel",
                      background=COLORS["surface"]).pack(side="left")
            return
        for item in reversed(view.stack):
            text = f"{item.source.name} → {', '.join(item.targets) or 'no target'}"
            tk.Label(self.stack_zone, text=text, bg=COLORS["surface_raised"],
                     fg=COLORS["text"], padx=9, pady=6).pack(side="left", padx=(0, 7))

    def _render_actions(self, view: GameView) -> None:
        self._clear_frame(self.action_frame)

        def add(label: str, command, *, accent: bool = False) -> None:
            ttk.Button(self.action_frame, text=label,
                       style="Accent.TButton" if accent else "TButton",
                       command=command).pack(fill="x", pady=(0, 6))

        selected = tuple(sorted(self._selected))
        actions = available_actions(view, selected)
        if self.game_over:
            add("Start another game", self._ready_again, accent=True)
            return
        if "keep" in actions:
            add("Keep hand", lambda: self._send("keep", selected), accent=True)
            add("Take mulligan", lambda: self._send("mulligan", ()))
            return
        if view.lifecycle != "PLAYING":
            ttk.Label(self.action_frame, text="Waiting for match setup.", style="Muted.TLabel",
                      background=COLORS["surface"], wraplength=240).pack(anchor="w")
            return

        if self._priority_pass_pending:
            ttk.Label(
                self.action_frame,
                text="Passing priority... Waiting for the server.",
                style="Muted.TLabel", background=COLORS["surface"], wraplength=240,
            ).pack(anchor="w")
            return

        if "pass_priority" in actions:
            add("Pass priority", lambda: self._send("pass_priority", ()), accent=True)
        selected_hand = [card for card in view.hand if card.instance_id in self._selected]
        selected_own = [card for card in view.player.battlefield if card.instance_id in self._selected]
        if "play_land" in actions:
            add("Play selected land", lambda: self._send(
                "play_land", (selected_hand[0].instance_id,)))
        if "cast_spell" in actions:
            add("Cast selected spell", lambda: self._cast(selected_hand[0]))
        if "discard" in actions:
            add("Discard selected", lambda: self._send(
                "discard", tuple(card.instance_id for card in selected_hand)))
        if "declare_attackers" in actions:
            add("Declare selected attackers", lambda: self._send("declare_attackers", selected_own))
        if "declare_blockers" in actions:
            add("Declare blockers" if selected_own else "Declare no blockers", self._declare_blockers)
        if "assign_damage_order" in actions:
            add("Assign damage order", self._assign_damage_order)
        if not self.action_frame.winfo_children():
            ttk.Label(self.action_frame, text="Select a card or wait for priority.",
                      style="Muted.TLabel", background=COLORS["surface"],
                      wraplength=240).pack(anchor="w")

    def _cast(self, card: CardView) -> None:
        if self.current_view is None:
            return
        definition = self.catalog.card(card.instance_id)
        options = legal_target_options(self.current_view, definition)
        targets: list[str] = []
        if card.base_id in {"lightning_bolt", "counterspell", "unsummon", "giant_growth"}:
            if not options:
                self.status_var.set("This spell currently has no legal target.")
                return
            target = self._choose_one("Choose target", "Choose the spell's target:", options)
            if target is None:
                return
            targets.append(target)
        mana = ", ".join(
            f"{'generic' if key == 'generic' else key}={amount}"
            for key, amount in card.mana_cost.items()
        )
        self._send("cast_spell", (card.instance_id,),
                   {"targets": ",".join(targets), "mana": mana})

    def _declare_blockers(self) -> None:
        if self.current_view is None:
            return
        blockers = [card for card in self.current_view.player.battlefield
                    if card.instance_id in self._selected]
        attacker_ids = list(self.current_view.combat.get("attackers", ()))
        mapping = self._choose_blocker_map(blockers, attacker_ids)
        if mapping is not None:
            self._send("declare_blockers", (), {"blockers": mapping})

    def _assign_damage_order(self) -> None:
        if self.current_view is None:
            return
        groups = self.current_view.combat.get("blockers", {})
        attackers = [(attacker, self._card_label(attacker)) for attacker in groups]
        attacker = (attackers[0][0] if len(attackers) == 1 else
                    self._choose_one("Damage order", "Choose the attacker:", tuple(attackers)))
        if attacker is None:
            return
        blocker_ids = list(groups.get(attacker, ()))
        order = self._order_choices(
            "Damage order", "Move blockers into damage order:",
            [(card_id, self._card_label(card_id)) for card_id in blocker_ids],
        )
        if order is not None:
            self._send("assign_damage_order", (attacker,), {"order_ids": order})

    def _card_label(self, card_id: str) -> str:
        if self.current_view is not None:
            for card in (*self.current_view.hand, *self.current_view.player.battlefield,
                         *self.current_view.opponent.battlefield):
                if card.instance_id == card_id:
                    return card.name
        try:
            return self.catalog.card(card_id).name
        except KeyError:
            return "Card"

    def _choose_one(self, title: str, prompt: str,
                    options: tuple[tuple[str, str], ...]) -> str | None:
        if not options:
            return None
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg=COLORS["surface"])
        dialog.transient(self.root)
        dialog.grab_set()
        result: list[str] = []
        labels = [f"{index}. {label}" for index, (_value, label) in enumerate(options, 1)]
        ttk.Label(dialog, text=prompt, style="Section.TLabel",
                  background=COLORS["surface"]).pack(anchor="w", padx=18, pady=(18, 10))
        choice = tk.StringVar(value=labels[0])
        combo = ttk.Combobox(dialog, textvariable=choice, values=labels,
                             state="readonly", width=42)
        combo.pack(fill="x", padx=18)
        combo.focus_set()

        def accept() -> None:
            result.append(options[labels.index(choice.get())][0])
            dialog.destroy()

        ttk.Button(dialog, text="Choose", style="Accent.TButton", command=accept).pack(
            fill="x", padx=18, pady=18)
        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        self.root.wait_window(dialog)
        return result[0] if result else None

    def _order_choices(self, title: str, prompt: str,
                       options: list[tuple[str, str]]) -> list[str] | None:
        if len(options) <= 1:
            return [value for value, _label in options]
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.configure(bg=COLORS["surface"])
        dialog.transient(self.root)
        dialog.grab_set()
        ordered = list(options)
        result: list[list[str]] = []
        ttk.Label(dialog, text=prompt, style="Section.TLabel",
                  background=COLORS["surface"]).pack(anchor="w", padx=18, pady=(18, 10))
        listing = tk.Listbox(dialog, height=min(8, len(ordered)), bg="#121819",
                             fg=COLORS["text"], selectbackground=COLORS["accent_dark"],
                             relief="flat", font=("Segoe UI", 10))
        listing.pack(fill="both", expand=True, padx=18)

        def redraw(index: int = 0) -> None:
            listing.delete(0, "end")
            for position, (_value, label) in enumerate(ordered, 1):
                listing.insert("end", f"{position}. {label}")
            listing.selection_set(index)

        def move(offset: int) -> None:
            selected = listing.curselection()
            if not selected:
                return
            source = selected[0]
            target = max(0, min(len(ordered) - 1, source + offset))
            if source != target:
                ordered.insert(target, ordered.pop(source))
                redraw(target)

        controls = tk.Frame(dialog, bg=COLORS["surface"])
        controls.pack(fill="x", padx=18, pady=10)
        ttk.Button(controls, text="Move up", command=lambda: move(-1)).pack(side="left")
        ttk.Button(controls, text="Move down", command=lambda: move(1)).pack(side="left", padx=7)

        def accept() -> None:
            result.append([value for value, _label in ordered])
            dialog.destroy()

        ttk.Button(dialog, text="Confirm order", style="Accent.TButton", command=accept).pack(
            fill="x", padx=18, pady=(0, 18))
        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Up>", lambda _event: (move(-1), "break")[1])
        dialog.bind("<Down>", lambda _event: (move(1), "break")[1])
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        redraw()
        listing.focus_set()
        self.root.wait_window(dialog)
        return result[0] if result else None

    def _choose_blocker_map(self, blockers: list[CardView],
                            attacker_ids: list[str]) -> dict[str, list[str]] | None:
        if not blockers:
            return {}
        if not attacker_ids:
            self.status_var.set("No attackers are available to block.")
            return None
        dialog = tk.Toplevel(self.root)
        dialog.title("Declare blockers")
        dialog.configure(bg=COLORS["surface"])
        dialog.transient(self.root)
        dialog.grab_set()
        placeholder = "Choose attacker..."
        attacker_labels = [f"{index}. {self._card_label(card_id)}"
                           for index, card_id in enumerate(attacker_ids, 1)]
        attacker_by_label = dict(zip(attacker_labels, attacker_ids))
        choices: list[tk.StringVar] = []
        combos: list[ttk.Combobox] = []
        ttk.Label(dialog, text="Choose what each selected creature blocks.",
                  style="Section.TLabel", background=COLORS["surface"]).grid(
                      row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 10))
        for row, blocker in enumerate(blockers, 1):
            ttk.Label(dialog, text=blocker.name, background=COLORS["surface"]).grid(
                row=row, column=0, sticky="w", padx=(18, 12), pady=5)
            choice = tk.StringVar(value=placeholder)
            choices.append(choice)
            combo = ttk.Combobox(dialog, textvariable=choice,
                                 values=(placeholder, *attacker_labels),
                                 state="readonly", width=34)
            combo.grid(row=row, column=1, padx=(0, 18), pady=5)
            combos.append(combo)
        result: list[dict[str, list[str]]] = []
        error_var = tk.StringVar(value="")
        ttk.Label(dialog, textvariable=error_var, background=COLORS["surface"],
                  foreground=COLORS["danger"]).grid(
                      row=len(blockers) + 1, column=0, columnspan=2, sticky="w",
                      padx=18, pady=(8, 0))

        def accept() -> None:
            try:
                mapping = build_blocker_mapping(
                    [blocker.instance_id for blocker in blockers],
                    [attacker_by_label.get(choice.get()) for choice in choices],
                )
            except ValueError as exc:
                error_var.set(str(exc))
                return
            result.append(mapping)
            dialog.destroy()

        ttk.Button(dialog, text="Declare blockers", style="Accent.TButton", command=accept).grid(
            row=len(blockers) + 2, column=0, columnspan=2, sticky="ew", padx=18, pady=18)
        dialog.bind("<Return>", lambda _event: accept())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        combos[0].focus_set()
        self.root.wait_window(dialog)
        return result[0] if result else None

    def _send(self, action: str, selected=(), fields=None) -> None:
        if self.controller is None:
            self.status_var.set("Not connected to a match.")
            return
        selected_ids = tuple(
            item.instance_id if isinstance(item, CardView) else str(item) for item in selected
        )
        try:
            pdu = dispatch_gui_action(self.controller, action, selected_ids, fields)
        except (ConnectionError, OSError) as exc:
            self._connection_failed(exc, self.network)
            return
        except (TypeError, ValueError) as exc:
            self.status_var.set(str(exc))
            return
        if action == "pass_priority":
            self._priority_pass_pending = True
            self.priority_var.set("Passing priority...")
            if self.current_view is not None:
                self._render_actions(self.current_view)
        self._append_log(f"Sent {pdu['type']}.")
        self.status_var.set("Action sent. Waiting for the authoritative update.")

    def _handle_event(self, pdu: dict[str, object]) -> None:
        if not self._game_screen_active:
            return
        pdu_type = str(pdu.get("type", "EVENT"))
        self._append_log(self._event_summary(pdu))
        if pdu_type == "TRIGGER_ORDER":
            trigger_ids = [str(item) for item in pdu.get("trigger_ids", ())]
            order = self._order_choices(
                "Order triggers", "Move triggered abilities into resolution order:",
                [(trigger_id, "Triggered ability") for trigger_id in trigger_ids],
            )
            if order is not None:
                self._send("trigger_order", (), {"order": ",".join(order)})
        elif pdu_type == "TRIGGER_CHOICE":
            accept = messagebox.askyesno("Triggered ability", str(pdu.get("effect_summary", "Use trigger?")),
                                         parent=self.root)
            target = ""
            if accept and pdu.get("requires_target"):
                legal_targets = tuple(
                    (str(item), self._card_label(str(item)))
                    for item in pdu.get("legal_targets", ())
                )
                target = self._choose_one("Choose target", "Choose the trigger's target:",
                                          legal_targets) or ""
            self._send("trigger_choice", (), {"trigger_id": pdu.get("trigger_id", ""),
                                               "accept": accept, "target": target})
        elif pdu_type == "GAME_OVER":
            self.game_over = True
            self.priority_var.set("Game over")
            self.status_var.set("Game over. Both players may ready the same decks for another game.")
            if self.current_view is not None:
                self._render_actions(self.current_view)

    def _handle_error(self, pdu: dict[str, object]) -> None:
        if not self._game_screen_active:
            return
        if self._priority_pass_pending:
            self._priority_pass_pending = False
            if self.current_view is not None:
                if self.current_view.has_priority:
                    self.priority_var.set("Your priority")
                elif self.current_view.priority_holder:
                    self.priority_var.set(f"Priority: {self.current_view.priority_holder}")
                else:
                    self.priority_var.set("Resolving state")
                self._render_actions(self.current_view)
        message = f"{pdu.get('code', 'ERROR')}: {pdu.get('message', 'Action rejected')}"
        self.status_var.set(message)
        self._append_log(message)

    @staticmethod
    def _event_summary(pdu: dict[str, object]) -> str:
        pdu_type = str(pdu.get("type", "EVENT"))
        if pdu_type == "PHASE_TRANSITION":
            return f"Phase: {pdu.get('to_phase', '')}"
        if pdu_type == "PRIORITY_GRANT":
            return f"Priority granted to {pdu.get('player_id', '')}."
        if pdu_type == "GAME_OVER":
            return f"Game over: {pdu.get('winner_id', '')} wins ({pdu.get('reason', '')})."
        return pdu_type.replace("_", " ").title()

    def _append_log(self, message: str) -> None:
        self._activity_history = bounded_activity_history(
            self._activity_history, message, limit=ACTIVITY_LOG_LIMIT)
        if (not hasattr(self, "activity_log")
                or not self.activity_log.winfo_exists()):
            return
        self.activity_log.configure(state="normal")
        self.activity_log.delete("1.0", "end")
        self.activity_log.insert("end", "\n".join(self._activity_history))
        self._activity_empty = False
        self.activity_log.see("end")
        self.activity_log.configure(state="disabled")

    def _set_activity_empty_state(self) -> None:
        self._activity_history = ()
        self._activity_empty = True
        self.activity_log.configure(state="normal")
        self.activity_log.delete("1.0", "end")
        self.activity_log.insert("end", "No actions yet. Server events and rejected requests will appear here.")
        self.activity_log.configure(state="disabled")

    def _ready_again(self) -> None:
        if self.controller is None or not self.deck_list:
            self.status_var.set("The original deck is unavailable; reconnect to start another game.")
            return
        try:
            pdu = self.controller.ready(self.deck_list)
        except (ConnectionError, OSError) as exc:
            self._connection_failed(exc, self.network)
            return
        except ValueError as exc:
            self.status_var.set(str(exc))
            return
        self.game_over = False
        if self.current_view is not None:
            self._render_actions(self.current_view)
        self._append_log(f"Sent {pdu['type']} for another game.")
        self.status_var.set("Ready for another game. Waiting for the other player.")

    def _confirm_concede(self) -> None:
        if messagebox.askyesno("Concede match", "Concede this game?", parent=self.root):
            self._send("concede")

    def _drain_bridge(self) -> None:
        if self._closing:
            return
        try:
            self.bridge.drain(self._bridge_error, max_callbacks=BRIDGE_CALLBACK_LIMIT)
        finally:
            if not self._closing:
                self.root.after(40, self._drain_bridge)

    def _bridge_error(self, exc: Exception) -> None:
        self.status_var.set(f"Could not process a server update: {exc}")
        self._append_log(f"Update error: {exc}")

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._connection_epoch += 1
        self._close_networks(self._pending_network, self.network)
        self._pending_network = None
        self.network = None
        self.controller = None
        self.store = None
        self.root.destroy()
