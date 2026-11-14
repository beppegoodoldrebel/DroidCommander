"""Cockpit-style dark theme for the editor (an original sci-fi look: deep-space panels,
amber instrument accents, cyan "hologram" highlights). No third-party assets."""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

C = {
    "bg": "#0a0e13",        # deep space
    "panel": "#111821",
    "field": "#0c131a",
    "border": "#263544",
    "text": "#d6e0e8",
    "dim": "#7d909f",
    "amber": "#ffb43a",     # instrument displays
    "amber_dark": "#3a2a10",
    "cyan": "#4fd1ff",      # hologram
    "ok": "#5ee08a",
    "warn": "#ff8a3d",
    "off": "#4a5865",
    "select": "#1f3d55",
}


def _icon(root, size=32):
    """Window icon: the same little astromech, drawn pixel by pixel (no image files)."""
    img = tk.PhotoImage(master=root, width=size, height=size)
    img.put(C["bg"], to=(0, 0, size, size))
    cx, r = size / 2, size * 0.42
    for y in range(size):                     # dome
        for x in range(size):
            d = ((x - cx) ** 2 + (y - size * 0.48) ** 2) ** 0.5
            if y < size * 0.48 and d <= r:
                img.put(C["cyan"] if d > r - 2 else C["panel"], (x, y))
    img.put(C["amber"], to=(int(cx - 3), int(size * 0.22), int(cx + 3), int(size * 0.36)))   # eye
    img.put(C["cyan"], to=(int(size * 0.16), int(size * 0.5), int(size * 0.84), int(size * 0.92)))
    img.put(C["panel"], to=(int(size * 0.16) + 2, int(size * 0.5) + 2, int(size * 0.84) - 2, int(size * 0.92) - 2))
    img.put(C["amber"], to=(int(size * 0.28), int(size * 0.62), int(size * 0.72), int(size * 0.67)))
    return img


def _pick(*families):
    available = set(tkfont.families())
    return next((f for f in families if f in available), "TkDefaultFont")


def apply(root):
    """Style every ttk widget. Returns the palette, plus the fonts as F."""
    head = _pick("Bahnschrift SemiBold", "Bahnschrift", "Segoe UI Semibold", "Segoe UI")
    body = _pick("Segoe UI", "Bahnschrift")
    mono = _pick("Consolas", "Cascadia Mono", "Courier New")
    F = {"head": (head, 10), "title": (head, 18), "sub": (head, 9), "body": (body, 10),
         "mono": (mono, 10), "big": (head, 20), "tab": (head, 10)}

    root.configure(bg=C["bg"])
    root._droid_icon = _icon(root)          # keep a reference, or Tk drops the image
    root.iconphoto(True, root._droid_icon)
    root.option_add("*TCombobox*Listbox.background", C["field"])
    root.option_add("*TCombobox*Listbox.foreground", C["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["select"])
    root.option_add("*TCombobox*Listbox.selectForeground", C["amber"])
    root.option_add("*TCombobox*Listbox.font", F["body"])

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=C["bg"], foreground=C["text"], fieldbackground=C["field"],
                bordercolor=C["border"], lightcolor=C["panel"], darkcolor=C["panel"],
                troughcolor=C["field"], focuscolor=C["amber"], selectbackground=C["select"],
                selectforeground=C["amber"], insertcolor=C["amber"], font=F["body"])
    s.configure("TFrame", background=C["bg"])
    s.configure("Panel.TFrame", background=C["panel"])
    s.configure("TLabel", background=C["bg"], foreground=C["text"])
    s.configure("Hint.TLabel", foreground=C["dim"])
    s.configure("Warn.TLabel", foreground=C["warn"])
    s.configure("Ok.TLabel", foreground=C["ok"])
    s.configure("Big.TLabel", foreground=C["amber"], font=F["big"])

    s.configure("TLabelframe", background=C["bg"], bordercolor=C["border"], relief="solid", borderwidth=1)
    s.configure("TLabelframe.Label", background=C["bg"], foreground=C["amber"], font=F["sub"])

    s.configure("TButton", background=C["panel"], foreground=C["text"], bordercolor=C["border"],
                padding=(10, 4), font=F["head"])
    s.map("TButton",
          background=[("pressed", C["amber"]), ("active", C["amber_dark"])],
          foreground=[("pressed", C["bg"]), ("active", C["amber"]), ("disabled", C["off"])],
          bordercolor=[("active", C["amber"]), ("focus", C["amber"])])
    s.configure("Accent.TButton", background=C["amber"], foreground=C["bg"], bordercolor=C["amber"])
    s.configure("Launch.TButton", background=C["amber"], foreground=C["bg"], bordercolor=C["amber"],
                font=(head, 14), padding=(26, 10))
    s.map("Launch.TButton", background=[("active", "#ffc866"), ("pressed", "#e09a20")],
          foreground=[("active", C["bg"])])
    s.map("Accent.TButton", background=[("active", "#ffc866"), ("pressed", "#e09a20")],
          foreground=[("active", C["bg"])])

    for w in ("TEntry", "TSpinbox", "TCombobox"):
        s.configure(w, fieldbackground=C["field"], foreground=C["text"], bordercolor=C["border"],
                    arrowcolor=C["amber"], background=C["panel"], padding=4)
        s.map(w, bordercolor=[("focus", C["amber"])], fieldbackground=[("readonly", C["field"])],
              foreground=[("readonly", C["text"])], selectbackground=[("readonly", C["field"])],
              selectforeground=[("readonly", C["amber"])])

    s.configure("TCheckbutton", background=C["bg"], foreground=C["text"], indicatorbackground=C["field"],
                indicatorforeground=C["amber"], indicatorcolor=C["field"])
    s.map("TCheckbutton", indicatorcolor=[("disabled", C["field"]), ("selected", C["amber"])],
          indicatorbackground=[("disabled", C["field"])],
          upperbordercolor=[("disabled", C["border"])], lowerbordercolor=[("disabled", C["border"])],
          foreground=[("disabled", C["off"]), ("active", C["amber"])],
          background=[("disabled", C["bg"]), ("active", C["bg"])])
    s.configure("TRadiobutton", background=C["bg"], foreground=C["text"], indicatorcolor=C["field"],
                indicatorbackground=C["field"], indicatorforeground=C["amber"],
                upperbordercolor=C["amber"], lowerbordercolor=C["amber"])
    s.map("TRadiobutton", indicatorcolor=[("selected", C["amber"])], foreground=[("active", C["amber"])],
          background=[("active", C["bg"])])

    s.configure("Horizontal.TScale", background=C["amber"], troughcolor=C["field"], bordercolor=C["border"],
                lightcolor=C["field"], darkcolor=C["field"], sliderlength=12, gripcount=0)
    s.map("Horizontal.TScale", background=[("active", "#ffc866")])
    s.configure("Vertical.TScrollbar", background=C["panel"], troughcolor=C["bg"], bordercolor=C["bg"],
                arrowcolor=C["dim"], lightcolor=C["panel"], darkcolor=C["panel"])
    s.map("Vertical.TScrollbar", background=[("active", C["border"])])

    s.configure("Treeview", background=C["field"], fieldbackground=C["field"], foreground=C["text"],
                bordercolor=C["border"], rowheight=24)
    s.map("Treeview", background=[("selected", C["select"])], foreground=[("selected", C["amber"])])
    s.configure("Treeview.Heading", background=C["panel"], foreground=C["cyan"], bordercolor=C["border"],
                font=F["sub"], relief="flat", padding=4)
    s.map("Treeview.Heading", background=[("active", C["panel"])])

    s.configure("TNotebook", background=C["bg"], bordercolor=C["border"], tabmargins=(8, 6, 8, 0))
    s.configure("TNotebook.Tab", background=C["bg"], foreground=C["dim"], bordercolor=C["border"],
                padding=(16, 6), font=F["tab"])
    s.map("TNotebook.Tab", background=[("selected", C["panel"])],
          foreground=[("selected", C["amber"]), ("active", C["text"])],
          lightcolor=[("selected", C["amber"])])
    s.layout("Tabless.TNotebook.Tab", [])            # pages only; TabBar draws the tabs
    s.configure("Tabless.TNotebook", background=C["bg"], borderwidth=0, tabmargins=0)
    s.configure("TPanedwindow", background=C["bg"])
    s.configure("Sash", sashthickness=6, gripcount=0, background=C["bg"])
    C["F"] = F
    return C


class TabBar(tk.Frame):
    """Big cockpit-style mode selector that drives a tab-less ttk.Notebook."""

    def __init__(self, parent, notebook):
        super().__init__(parent, bg=C["bg"])
        self.notebook = notebook
        self.tabs = []
        self.current = 0
        line = tk.Frame(parent, bg=C["border"], height=1)     # baseline under the whole bar
        self._line = line

    def pack_bar(self, **kw):
        self.pack(fill="x", **kw)
        self._line.pack(fill="x", padx=kw.get("padx", 0))

    def add(self, page, text, glyph=""):
        idx = len(self.tabs)
        self.notebook.add(page)
        cell = tk.Frame(self, bg=C["bg"], cursor="hand2")
        cell.pack(side="left", padx=(0, 4))
        label = tk.Label(cell, text=f"{glyph}  {' '.join(text.upper())}" if glyph else " ".join(text.upper()),
                         bg=C["bg"], fg=C["dim"], font=(C["F"]["head"][0], 13), padx=26, pady=10)
        label.pack()
        glow = tk.Frame(cell, bg=C["bg"], height=3)
        glow.pack(fill="x")
        for w in (cell, label):
            w.bind("<Button-1>", lambda e, i=idx: self.select(i))
            w.bind("<Enter>", lambda e, i=idx: self._hover(i, True))
            w.bind("<Leave>", lambda e, i=idx: self._hover(i, False))
        self.tabs.append((cell, label, glow))
        self._paint()
        return idx

    def select(self, idx):
        self.current = idx % len(self.tabs)
        self.notebook.select(self.current)
        self._paint()

    def step(self, delta):
        self.select(self.current + delta)
        return "break"

    def _hover(self, idx, on):
        if idx != self.current:
            cell, label, glow = self.tabs[idx]
            label.configure(fg=C["text"] if on else C["dim"])
            glow.configure(bg=C["border"] if on else C["bg"])

    def _paint(self):
        for i, (cell, label, glow) in enumerate(self.tabs):
            active = i == self.current
            bg = C["panel"] if active else C["bg"]
            cell.configure(bg=bg)
            label.configure(bg=bg, fg=C["amber"] if active else C["dim"])
            glow.configure(bg=C["amber"] if active else C["bg"])


def polish(widget):
    """Upper-case every frame title under `widget`, like labels on an instrument panel."""
    for w in widget.winfo_children():
        if w.winfo_class() == "TLabelframe":
            w.configure(text=str(w.cget("text")).upper())
        polish(w)


def style_text(widget):
    """tk.Text is not a ttk widget: colour it by hand."""
    widget.configure(bg=C["field"], fg=C["text"], insertbackground=C["amber"], selectbackground=C["select"],
                     selectforeground=C["amber"], relief="flat", highlightthickness=1,
                     highlightbackground=C["border"], highlightcolor=C["amber"], padx=6, pady=4,
                     font=C["F"]["body"])


def header(parent, title, subtitle):
    """Top bar: a small astromech glyph, the title and a subtitle, over an amber rule."""
    bar = tk.Frame(parent, bg=C["bg"])
    cv = tk.Canvas(bar, width=46, height=46, bg=C["bg"], highlightthickness=0)
    cv.pack(side="left", padx=(12, 10), pady=8)
    # dome, eye and body: a generic, original droid icon
    cv.create_arc(8, 6, 38, 34, start=0, extent=180, fill=C["panel"], outline=C["cyan"], width=2)
    cv.create_oval(19, 11, 27, 19, fill=C["amber"], outline="")
    cv.create_rectangle(10, 21, 36, 40, fill=C["panel"], outline=C["cyan"], width=2)
    cv.create_line(15, 27, 31, 27, fill=C["amber"], width=2)
    cv.create_line(15, 33, 25, 33, fill=C["cyan"], width=2)
    text = tk.Frame(bar, bg=C["bg"])
    text.pack(side="left", pady=6)
    tk.Label(text, text=" ".join(title.upper()), bg=C["bg"], fg=C["amber"], font=C["F"]["title"]).pack(anchor="w")
    bar.subtitle = tk.Label(text, text=subtitle.upper(), bg=C["bg"], fg=C["dim"], font=C["F"]["sub"])
    bar.subtitle.pack(anchor="w")
    rule = tk.Canvas(parent, height=3, bg=C["bg"], highlightthickness=0)

    def draw(_e=None):
        rule.delete("all")
        w = rule.winfo_width()
        rule.create_line(0, 1, w * 0.35, 1, fill=C["amber"], width=2)
        rule.create_line(w * 0.35 + 6, 1, w, 1, fill=C["border"], width=1)

    rule.bind("<Configure>", draw)
    return bar, rule
