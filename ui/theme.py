"""
G.O.B.L.I.N — Dark theme for plain tkinter + ttk.

Solid colours, no transparency.  Font size 12 base.
"""

import tkinter as tk
from tkinter import ttk

# ── Colours ───────────────────────────────────────────────────────────────────
BG      = "#1a1a1a"
PANEL   = "#212121"
DARK    = "#111111"
MID     = "#1e1e1e"
ROW_A   = "#1c1c1c"
ROW_B   = "#232323"

BLUE    = "#2563eb"
GREEN   = "#16a34a"
RED     = "#c92a2a"
ORANGE  = "#b45309"
TEAL    = "#0e7490"
TEXT    = "#e2e2e2"
DIM     = "#686868"
OK      = "#4ade80"
FAIL    = "#f87171"
WARNING = "#fbbf24"
SELECTED= "#2d2d2d"

# ── Fonts ─────────────────────────────────────────────────────────────────────
F_BASE  = ("Segoe UI",  12)
F_BOLD  = ("Segoe UI",  12, "bold")
F_BIG   = ("Segoe UI",  13, "bold")
F_TITLE = ("Segoe UI",  15, "bold")
F_SMALL = ("Segoe UI",  11)
F_TINY  = ("Segoe UI",  10)
F_MONO  = ("Consolas",  11)
F_MONO_S= ("Consolas",  10)

def row_bg(i: int) -> str:
    return ROW_A if i % 2 == 0 else ROW_B

# ── Scrollable frame helper ───────────────────────────────────────────────────

def make_scrollable(parent, bg: str = BG) -> tuple[tk.Frame, tk.Canvas]:
    """
    Returns (outer_frame, inner_frame).
    Pack / grid outer_frame; add widgets to inner_frame.
    Mousewheel scrolls automatically.
    """
    outer  = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0)
    vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)

    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas, bg=bg)
    wid   = canvas.create_window(0, 0, anchor="nw", window=inner)

    def _on_frame_cfg(e):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_cfg(e):
        canvas.itemconfig(wid, width=e.width)

    inner.bind("<Configure>", _on_frame_cfg)
    canvas.bind("<Configure>", _on_canvas_cfg)

    def _wheel(e):
        canvas.yview_scroll(-1 * (e.delta // 120), "units")

    canvas.bind("<Enter>",  lambda e: canvas.bind_all("<MouseWheel>", _wheel))
    canvas.bind("<Leave>",  lambda e: canvas.unbind_all("<MouseWheel>"))

    return outer, inner


# ── ttk Style ─────────────────────────────────────────────────────────────────

def configure_styles(root: tk.Tk):
    s = ttk.Style(root)
    s.theme_use("clam")

    # ── Global ────────────────────────────────────────────────────────────
    s.configure(".",
        background=BG, foreground=TEXT,
        font=F_BASE, borderwidth=0, relief="flat",
        troughcolor=DARK, selectbackground=SELECTED, selectforeground=TEXT,
    )

    # ── Frame ─────────────────────────────────────────────────────────────
    s.configure("TFrame",        background=BG)
    s.configure("Panel.TFrame",  background=PANEL)
    s.configure("Dark.TFrame",   background=DARK)
    s.configure("Mid.TFrame",    background=MID)

    # ── Label ─────────────────────────────────────────────────────────────
    s.configure("TLabel",        background=BG,    foreground=TEXT, font=F_BASE)
    s.configure("Dim.TLabel",    background=BG,    foreground=DIM,  font=F_SMALL)
    s.configure("Panel.TLabel",  background=PANEL, foreground=TEXT, font=F_BASE)
    s.configure("Dark.TLabel",   background=DARK,  foreground=TEXT, font=F_BASE)
    s.configure("Mid.TLabel",    background=MID,   foreground=TEXT, font=F_BASE)
    s.configure("Title.TLabel",  background=DARK,  foreground=TEXT, font=F_TITLE)
    s.configure("Mono.TLabel",   background=BG,    foreground=TEXT, font=F_MONO)
    s.configure("OK.TLabel",     background=BG,    foreground=OK,   font=F_BOLD)
    s.configure("Fail.TLabel",   background=BG,    foreground=FAIL, font=F_BOLD)

    # ── Button ────────────────────────────────────────────────────────────
    s.configure("TButton",
        background="#2a2a2a", foreground=TEXT, font=F_BASE,
        padding=(8, 4), relief="flat", borderwidth=0,
    )
    s.map("TButton",
        background=[("active", "#333333"), ("pressed", "#3d3d3d"), ("disabled", "#1a1a1a")],
        foreground=[("disabled", DIM)],
    )

    for name, bg, hover in [
        ("Blue.TButton",   BLUE,    "#1d4ed8"),
        ("Green.TButton",  GREEN,   "#15803d"),
        ("Red.TButton",    RED,     "#b91c1c"),
        ("Orange.TButton", ORANGE,  "#92400e"),
        ("Teal.TButton",   TEAL,    "#0c6880"),
        ("Dark.TButton",   "#2a2a2a", "#333333"),
    ]:
        s.configure(name, background=bg, foreground="white", font=F_BASE,
                    padding=(8, 4), relief="flat", borderwidth=0)
        s.map(name,
              background=[("active", hover), ("pressed", hover), ("disabled", "#1a1a1a")],
              foreground=[("disabled", DIM)])

    # Small button variants
    for name, bg, hover in [
        ("SmBlue.TButton",  BLUE,    "#1d4ed8"),
        ("SmGreen.TButton", GREEN,   "#15803d"),
        ("SmRed.TButton",   RED,     "#b91c1c"),
        ("SmTeal.TButton",  TEAL,    "#0c6880"),
        ("SmOrange.TButton",ORANGE,  "#92400e"),
        ("Sm.TButton",      "#2a2a2a","#333333"),
    ]:
        s.configure(name, background=bg, foreground="white", font=F_SMALL,
                    padding=(5, 2), relief="flat", borderwidth=0)
        s.map(name,
              background=[("active", hover), ("pressed", hover), ("disabled", "#1a1a1a")],
              foreground=[("disabled", DIM)])

    # ── Entry ─────────────────────────────────────────────────────────────
    s.configure("TEntry",
        fieldbackground="#252525", foreground=TEXT,
        insertcolor=TEXT, padding=4,
    )

    # ── Combobox ──────────────────────────────────────────────────────────
    s.configure("TCombobox",
        fieldbackground="#252525", foreground=TEXT,
        selectbackground="#252525", selectforeground=TEXT,
        arrowcolor=DIM, background="#252525", padding=4,
    )
    s.map("TCombobox",
        fieldbackground=[("readonly", "#252525"), ("disabled", "#1a1a1a")],
        foreground=[("disabled", DIM)],
    )

    # ── Notebook ──────────────────────────────────────────────────────────
    s.configure("TNotebook",     background=DARK, tabmargins=[0, 0, 0, 0])
    s.configure("TNotebook.Tab",
        background=DARK, foreground=DIM, font=F_SMALL,
        padding=(16, 7), borderwidth=0,
    )
    s.map("TNotebook.Tab",
        background=[("selected", SELECTED), ("active", "#1e1e1e")],
        foreground=[("selected", TEXT),     ("active", "#aaaaaa")],
    )

    # ── Scrollbar ─────────────────────────────────────────────────────────
    s.configure("TScrollbar",
        background="#2a2a2a", troughcolor=DARK,
        arrowcolor=DIM, borderwidth=0, relief="flat",
    )
    s.map("TScrollbar", background=[("active", "#3a3a3a")])

    # ── Scale / Slider ────────────────────────────────────────────────────
    s.configure("TScale",
        background=BG, troughcolor="#333333",
        sliderthickness=18, sliderrelief="flat",
    )

    # ── Separator ─────────────────────────────────────────────────────────
    s.configure("TSeparator", background="#2a2a2a")
