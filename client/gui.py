"""Tkinter presentation adapter for the MTGNP client layers.

DIRECTION CONTRACT
THESIS: A quiet tabletop control surface makes server authority and player choices obvious; it refuses ornamental fantasy chrome.
OWN-WORLD: Charcoal and felt surfaces, warm parchment headings, teal priority cues, thin structural borders, and real card frames.
STORY: Connect, recognize the match state, select cards, act through the protocol, and see the authoritative response.
FIRST VIEWPORT: Turn phases left, two battlefields and stack centered, hand anchored below, contextual actions and history right.
FORM: Quiet Tabletop, fourth grounded direction, seed 1dc2138b.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from client.controller import ClientController
from client.gui_actions import dispatch_gui_action
from client.gui_model import (
    CardCatalog,
    CardView,
    GameView,
    GuiEventBridge,
    PHASE_LABELS,
    available_actions,
    legal_target_options,
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
}

PHASES = tuple(PHASE_LABELS)


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
        self._card_widgets: dict[str, tk.Frame] = {}
        self._images: dict[tuple[str, str], tk.PhotoImage] = {}
        self._closing = False

        self.phase_var = tk.StringVar(value="Waiting for game state")
        self.turn_var = tk.StringVar(value="Turn —")
        self.priority_var = tk.StringVar(value="Not connected")
        self.status_var = tk.StringVar(value="Enter your connection details.")
        self.selection_var = tk.StringVar(value="No cards selected")
        self.player_summary_var = tk.StringVar(value="You")
        self.opponent_summary_var = tk.StringVar(value="Opponent")

        self.root.title("MTGNP — Quiet Tabletop")
        self.root.geometry("1400x900")
        self.root.minsize(1080, 720)
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

    def _clear_root(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()

    def _show_connection(self, host: str, port: int, player_id: str, deck_path: str) -> None:
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

        self.connect_button.state(["disabled"])
        self.status_var.set("Connecting to the server…")
        network = ClientNetwork(host, port, verbose=self.verbose,
                                heartbeat_interval=5, heartbeat_timeout=15)
        store = ClientStateStore()
        controller = ClientController(player_id, network, store)
        network.subscribe(lambda pdu: self.bridge.post(store.apply_pdu, pdu))
        network.subscribe_disconnect(lambda exc: self.bridge.post(self._connection_failed, exc))

        def connect_worker() -> None:
            try:
                network.connect()
            except (ConnectionError, OSError) as exc:
                self.bridge.post(self._connection_failed, exc)
                return
            self.bridge.post(self._finish_connection, player_id, deck, controller, store, network)

        threading.Thread(target=connect_worker, name="mtgnp-gui-connect", daemon=True).start()

    def _finish_connection(self, player_id: str, deck: list[str], controller,
                           store: ClientStateStore, network) -> None:
        self.attach_session(player_id, controller, store, network, deck_list=deck)
        try:
            controller.ready(deck)
            self._append_log("Connected. Deck submitted to the server.")
        except (ConnectionError, OSError) as exc:
            self._connection_failed(exc)

    def _connection_failed(self, exc: Exception) -> None:
        if self._closing:
            return
        self.status_var.set(f"Connection failed: {exc}. Check the server address and try again.")
        if hasattr(self, "connect_button") and self.connect_button.winfo_exists():
            self.connect_button.state(["!disabled"])
        if hasattr(self, "activity_log") and self.activity_log.winfo_exists():
            self._append_log(f"Disconnected: {exc}")
            self.priority_var.set("Disconnected")

    def attach_session(self, player_id: str, controller, store: ClientStateStore, network,
                       *, deck_list: list[str] | None = None) -> None:
        self.player_id = player_id
        self.controller = controller
        self.store = store
        self.network = network
        if deck_list is not None:
            self.deck_list = list(deck_list)
        store.subscribe_state(self._render_state)
        store.subscribe_event(self._handle_event)
        store.subscribe_error(self._handle_error)
        self._build_game_screen()

    def _build_game_screen(self) -> None:
        self._clear_root()
        shell = ttk.Frame(self.root, padding=(16, 12, 16, 14))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)

        header = tk.Frame(shell, bg=COLORS["surface"], highlightthickness=1,
                          highlightbackground=COLORS["border"], padx=16, pady=10)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        header.columnconfigure(1, weight=1)
        brand = tk.Frame(header, bg=COLORS["surface"])
        brand.grid(row=0, column=0, sticky="w")
        ttk.Label(brand, text="MTGNP", style="Title.TLabel", background=COLORS["surface"]).pack(
            side="left")
        ttk.Label(brand, textvariable=self.turn_var, style="Muted.TLabel",
                  background=COLORS["surface"]).pack(side="left", padx=(12, 0), pady=(7, 0))
        ttk.Label(header, textvariable=self.phase_var, style="Section.TLabel",
                  background=COLORS["surface"]).grid(row=0, column=1)
        ttk.Label(header, textvariable=self.priority_var, style="Status.TLabel",
                  background=COLORS["surface"]).grid(row=0, column=2, sticky="e")

        self.phase_rail = tk.Frame(shell, bg=COLORS["surface"], highlightthickness=1,
                                   highlightbackground=COLORS["border"], padx=10, pady=12)
        self.phase_rail.grid(row=1, column=0, sticky="ns", padx=(0, 10))
        ttk.Label(self.phase_rail, text="Turn phases", style="Section.TLabel",
                  background=COLORS["surface"]).pack(anchor="w", pady=(0, 10))
        self.phase_labels: dict[str, tk.Label] = {}
        for phase in PHASES:
            label = tk.Label(self.phase_rail, text=PHASE_LABELS[phase], anchor="w",
                             bg=COLORS["surface"], fg=COLORS["faint"],
                             font=("Segoe UI", 9), padx=8, pady=4, width=20)
            label.pack(fill="x")
            self.phase_labels[phase] = label

        board = tk.Frame(shell, bg=COLORS["felt"], highlightthickness=1,
                         highlightbackground=COLORS["border"], padx=12, pady=10)
        board.grid(row=1, column=1, sticky="nsew")
        board.columnconfigure(0, weight=1)
        board.rowconfigure(1, weight=1)
        board.rowconfigure(3, weight=1)

        self.opponent_header = ttk.Label(board, textvariable=self.opponent_summary_var,
                                         style="Section.TLabel", background=COLORS["felt"])
        self.opponent_header.grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.opponent_zone = self._card_strip(board, 1)

        self.stack_zone = tk.Frame(board, bg=COLORS["surface"], highlightthickness=1,
                                   highlightbackground="#586765", padx=10, pady=8)
        self.stack_zone.grid(row=2, column=0, sticky="ew", pady=9)

        self.player_zone = self._card_strip(board, 3)
        ttk.Label(board, textvariable=self.player_summary_var, style="Section.TLabel",
                  background=COLORS["felt"]).grid(row=4, column=0, sticky="w", pady=(5, 4))

        hand_panel = tk.Frame(board, bg=COLORS["surface"], highlightthickness=1,
                              highlightbackground="#655b43", padx=8, pady=7)
        hand_panel.grid(row=5, column=0, sticky="ew", pady=(5, 0))
        hand_panel.columnconfigure(0, weight=1)
        ttk.Label(hand_panel, text="Your hand", style="Section.TLabel",
                  background=COLORS["surface"]).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.hand_zone = self._card_strip(hand_panel, 1, surface=COLORS["surface"])

        side = tk.Frame(shell, bg=COLORS["surface"], highlightthickness=1,
                        highlightbackground=COLORS["border"], padx=12, pady=12, width=285)
        side.grid(row=1, column=2, sticky="nsew", padx=(10, 0))
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

        footer = ttk.Label(shell, textvariable=self.status_var, style="Muted.TLabel")
        footer.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(9, 0))
        self.status_var.set("Connected. Waiting for the server's game state.")

    def _card_strip(self, parent, row: int, *, surface: str | None = None) -> tk.Frame:
        surface = surface or COLORS["felt"]
        container = tk.Frame(parent, bg=surface)
        container.grid(row=row, column=0, sticky="nsew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        canvas = tk.Canvas(container, bg=surface, highlightthickness=0, height=158)
        scrollbar = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview,
                                  style="Dark.Horizontal.TScrollbar")
        canvas.configure(xscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=0, sticky="ew")
        inner = tk.Frame(canvas, bg=surface)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        def refresh_scrollbar() -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            if inner.winfo_reqwidth() <= canvas.winfo_width():
                scrollbar.grid_remove()
            else:
                scrollbar.grid()

        def inner_changed(_event) -> None:
            refresh_scrollbar()

        def canvas_changed(event) -> None:
            canvas.itemconfigure(window, height=max(event.height, inner.winfo_reqheight()))
            refresh_scrollbar()

        inner.bind("<Configure>", inner_changed)
        canvas.bind("<Configure>", canvas_changed)
        return inner

    @staticmethod
    def _clear_frame(frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _render_state(self, state: dict[str, object]) -> None:
        try:
            view = GameView.from_state(self.player_id, state, self.catalog)
        except (KeyError, TypeError, ValueError) as exc:
            self.status_var.set(f"Cannot display the latest state: {exc}")
            return
        self.current_view = view
        if view.lifecycle in {"MULLIGAN", "PLAYING"}:
            self.game_over = False
        visible_ids = {
            card.instance_id for card in (*view.hand, *view.player.battlefield,
                                          *view.opponent.battlefield)
        }
        self._selected.intersection_update(visible_ids)
        self.phase_var.set(view.phase_label)
        self.turn_var.set(f"Turn {view.turn}")
        if view.has_priority:
            self.priority_var.set("Your priority")
        elif view.priority_holder:
            self.priority_var.set(f"Priority: {view.priority_holder}")
        else:
            self.priority_var.set("Resolving state")
        self.player_summary_var.set(
            f"You — {view.player.life} life · {view.player.library_count} library · "
            f"{view.player.graveyard_count} graveyard"
        )
        self.opponent_summary_var.set(
            f"{view.opponent.player_id} — {view.opponent.life} life · "
            f"{view.opponent.hand_count} hand · {view.opponent.library_count} library"
        )
        for phase, label in self.phase_labels.items():
            active = phase == view.phase
            label.configure(
                bg=COLORS["accent_dark"] if active else COLORS["surface"],
                fg="#effffc" if active else COLORS["faint"],
                font=("Segoe UI Semibold" if active else "Segoe UI", 9),
            )
        self._render_cards(self.opponent_zone, view.opponent.battlefield)
        self._render_cards(self.player_zone, view.player.battlefield)
        self._render_cards(self.hand_zone, view.hand)
        self._render_stack(view)
        self._render_actions(view)
        self.status_var.set("State synchronized with the server.")

    def _render_cards(self, frame: tk.Frame, cards: tuple[CardView, ...]) -> None:
        self._clear_frame(frame)
        if not cards:
            tk.Label(frame, text="No cards in this zone", bg=frame.cget("bg"),
                     fg=COLORS["faint"], font=("Segoe UI", 9)).pack(anchor="w", padx=8, pady=16)
            return
        for card in cards:
            border_color = (COLORS["accent"] if card.instance_id in self._selected
                            else COLORS["warm"] if card.tapped else COLORS["border"])
            tile = tk.Frame(frame, bg=border_color, padx=3 if card.tapped else 2,
                            pady=3 if card.tapped else 2)
            tile.pack(side="left", padx=(0, 8), pady=2)
            image = self._card_image(card.base_id, "small")
            button = tk.Button(
                tile,
                image=image,
                text=card.name if image is None else "",
                compound="top",
                command=lambda card_id=card.instance_id: self._toggle_card(card_id),
                bg=COLORS["surface_raised"], fg=COLORS["text"], activebackground="#354140",
                activeforeground=COLORS["text"], relief="flat", bd=0,
                width=120 if image is None else 0, height=9 if image is None else 0,
                cursor="hand2",
            )
            button.pack()
            button.bind("<Double-Button-1>", lambda _event, item=card: self._show_card_detail(item))
            status = []
            if card.tapped:
                status.append("Tapped")
            if card.damage:
                status.append(f"{card.damage} damage")
            tk.Label(tile, text=" · ".join(status) or card.card_type,
                     bg=COLORS["surface_raised"], fg=COLORS["warm"] if status else COLORS["muted"],
                     font=("Segoe UI Semibold", 8), width=12, anchor="w").pack(fill="x", padx=3, pady=3)
            self._card_widgets[card.instance_id] = tile

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
                image = image.subsample(3, 3)
        except tk.TclError:
            return None
        self._images[key] = image
        return image

    def _toggle_card(self, card_id: str) -> None:
        if card_id in self._selected:
            self._selected.remove(card_id)
        else:
            self._selected.add(card_id)
        self.selection_var.set(
            ", ".join(sorted(self._selected)) if self._selected else "No cards selected"
        )
        if self.current_view is not None:
            self._render_cards(self.opponent_zone, self.current_view.opponent.battlefield)
            self._render_cards(self.player_zone, self.current_view.player.battlefield)
            self._render_cards(self.hand_zone, self.current_view.hand)
            self._render_actions(self.current_view)

    def _show_card_detail(self, card: CardView) -> None:
        window = tk.Toplevel(self.root)
        window.title(card.name)
        window.configure(bg=COLORS["surface"])
        window.resizable(False, False)
        panel = tk.Frame(window, bg=COLORS["surface"], padx=16, pady=16)
        panel.pack()
        image = self._card_image(card.base_id, "full")
        if image is not None:
            tk.Label(panel, image=image, bg=COLORS["surface"]).grid(row=0, column=0, rowspan=5)
        ttk.Label(panel, text=card.name, style="Title.TLabel",
                  background=COLORS["surface"], wraplength=300).grid(
                      row=0, column=1, sticky="nw", padx=(18, 0))
        ttk.Label(panel, text=f"{card.card_type} {card.subtype}".strip(), style="Muted.TLabel",
                  background=COLORS["surface"], wraplength=300).grid(
                      row=1, column=1, sticky="nw", padx=(18, 0), pady=(8, 0))
        ttk.Label(panel, text=card.effect, background=COLORS["surface"], wraplength=300,
                  justify="left").grid(row=2, column=1, sticky="nw", padx=(18, 0), pady=(14, 0))
        if card.power is not None:
            ttk.Label(panel, text=f"Power / toughness: {card.power} / {card.toughness}",
                      background=COLORS["surface"]).grid(
                          row=3, column=1, sticky="nw", padx=(18, 0), pady=(14, 0))

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
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        redraw()
        self.root.wait_window(dialog)
        return result[0] if result else None

    def _choose_blocker_map(self, blockers: list[CardView],
                            attacker_ids: list[str]) -> dict[str, list[str]] | None:
        if not blockers:
            return {}
        dialog = tk.Toplevel(self.root)
        dialog.title("Declare blockers")
        dialog.configure(bg=COLORS["surface"])
        dialog.transient(self.root)
        dialog.grab_set()
        attacker_labels = [f"{index}. {self._card_label(card_id)}"
                           for index, card_id in enumerate(attacker_ids, 1)]
        choices: list[tk.StringVar] = []
        ttk.Label(dialog, text="Choose what each selected creature blocks.",
                  style="Section.TLabel", background=COLORS["surface"]).grid(
                      row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 10))
        for row, blocker in enumerate(blockers, 1):
            ttk.Label(dialog, text=blocker.name, background=COLORS["surface"]).grid(
                row=row, column=0, sticky="w", padx=(18, 12), pady=5)
            choice = tk.StringVar(value=attacker_labels[0])
            choices.append(choice)
            ttk.Combobox(dialog, textvariable=choice, values=attacker_labels,
                         state="readonly", width=34).grid(row=row, column=1, padx=(0, 18), pady=5)
        result: list[dict[str, list[str]]] = []

        def accept() -> None:
            mapping: dict[str, list[str]] = {}
            for blocker, choice in zip(blockers, choices):
                attacker = attacker_ids[attacker_labels.index(choice.get())]
                mapping.setdefault(attacker, []).append(blocker.instance_id)
            result.append(mapping)
            dialog.destroy()

        ttk.Button(dialog, text="Declare blockers", style="Accent.TButton", command=accept).grid(
            row=len(blockers) + 1, column=0, columnspan=2, sticky="ew", padx=18, pady=18)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
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
        except (ConnectionError, OSError, TypeError, ValueError) as exc:
            self.status_var.set(str(exc))
            return
        self._append_log(f"Sent {pdu['type']}.")
        self.status_var.set("Action sent. Waiting for the authoritative update.")

    def _handle_event(self, pdu: dict[str, object]) -> None:
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
        if not hasattr(self, "activity_log"):
            return
        self.activity_log.configure(state="normal")
        if getattr(self, "_activity_empty", False):
            self.activity_log.delete("1.0", "end")
            self._activity_empty = False
        self.activity_log.insert("end", f"{message}\n")
        self.activity_log.see("end")
        self.activity_log.configure(state="disabled")

    def _set_activity_empty_state(self) -> None:
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
        except (ConnectionError, OSError, ValueError) as exc:
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
            self.bridge.drain(self._bridge_error)
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
        if self.network is not None:
            self.network.close()
        self.root.destroy()
