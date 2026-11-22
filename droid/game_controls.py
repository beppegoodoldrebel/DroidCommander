"""Commands tab helpers: turn the game's controls into voice commands."""

import re
import tkinter as tk
from tkinter import ttk

from . import theme
from .phrases import normalize

# never offered as voice commands: held while flying, or dangerous to trigger by mistake
NOT_FOR_VOICE = {"FIRE_PRIMARY", "FIRE_SECONDARY", "FORWARD_THRUST", "REVERSE_THRUST", "BANK_LEFT",
                 "BANK_RIGHT", "PITCH_FORWARD", "PITCH_BACK", "YAW_LEFT", "YAW_RIGHT",
                 "GLIDE_WHEN_PRESSED", "BANK_WHEN_PRESSED", "VIEW_SLEW", "RIGHT_SLIDE_THRUST",
                 "LEFT_SLIDE_THRUST", "UP_SLIDE_THRUST", "DOWN_SLIDE_THRUST", "MULTI_SELF_DESTRUCT",
                 "MULTI_OBSERVER_ZOOM_TO"}


def phrase_from_label(label):
    """'Engage Hyperdrive (End Mission)' -> 'engage hyperdrive'"""
    t = re.sub(r"\(.*?\)", " ", label).replace("&", " and ")
    t = re.sub(r"^\s*wingmen\s*:\s*", "", t, flags=re.I)
    return normalize(re.sub(r"[-_/:>]", " ", t))


def phrases_from_label(label):
    """A few ways of saying a control's label: 'Toggle S-foils' -> ['toggle s foils', 's foils']."""
    first = phrase_from_label(label)
    out = [first]
    words = first.split()
    if len(words) > 1 and words[0] in ("toggle", "cycle", "target", "show"):
        rest = " ".join(words[1:]) if words[0] == "toggle" else None
        if rest:
            out.append(rest)
    return out


class ImportDialog(tk.Toplevel):
    """Tick game controls to turn them into voice commands."""

    def __init__(self, parent, editor):
        super().__init__(parent)
        self.configure(bg=theme.C["bg"])
        self.title("Import commands from the game")
        self.transient(parent)
        self.ed = editor
        self.result = None
        self.selected = set()
        cat = editor.catalog
        used = {a.get("bind") for c in editor.commands for a in c.get("actions", [])}
        self.rows = []
        for name in cat.names():
            if name in NOT_FOR_VOICE:
                continue
            if name in used:
                status = "already a command"
            elif cat.disabled(name):
                status = "off in this mod"
            else:
                status = "ready"
            source = "Fate of the Galaxy" if cat.from_mod(name) else "FreeSpace Open"
            self.rows.append((name, cat.label(name), source, status))
        # the mod's own controls first (that's where new ones appear), then alphabetical
        self.rows.sort(key=lambda x: (x[3] != "ready", x[2] != "Fate of the Galaxy", x[1].lower()))

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="The game's controls. Click to tick the ones you want as voice commands; each "
                            "gets phrases from its name, which you can edit later. They are pressed inside "
                            "the game by the game link, whatever key (or none) they have.",
                  style="Hint.TLabel", wraplength=760).pack(anchor="w")
        top = ttk.Frame(frm)
        top.pack(fill="x", pady=8)
        ttk.Label(top, text="Search:").pack(side="left")
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.fill())
        ttk.Entry(top, textvariable=self.filter, width=30).pack(side="left", padx=6)
        ttk.Button(top, text="Select none", command=self.select_none).pack(side="left", padx=(12, 0))
        bottom = ttk.Frame(frm)
        bottom.pack(side="bottom", fill="x", pady=(10, 0))   # always visible
        tf = ttk.Frame(frm)
        tf.pack(fill="both", expand=True)
        cols = ("sel", "label", "source", "status")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=12, selectmode="none")
        for c, text, w, anchor in (("sel", "", 40, "center"), ("label", "Game control", 330, "w"),
                                   ("source", "Named by", 170, "w"), ("status", "Status", 150, "w")):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor=anchor, stretch=c == "label")
        self.tree.tag_configure("ready", foreground=theme.C["text"])
        self.tree.tag_configure("picked", foreground=theme.C["amber"])
        self.tree.tag_configure("off", foreground=theme.C["off"])
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tree.bind("<Button-1>", self.on_click)
        self.count = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.count.pack(side="left")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        self.ok_btn = ttk.Button(bottom, text="Add", style="Accent.TButton", command=self.ok)
        self.ok_btn.pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.destroy())
        self.fill()
        theme.polish(self)

    def fill(self):
        f = self.filter.get().lower().strip()
        self.tree.delete(*self.tree.get_children())
        for name, label, source, status in self.rows:
            if f and f not in label.lower() and f not in name.lower():
                continue
            picked = name in self.selected
            tag = "picked" if picked else ("ready" if status == "ready" else "off")
            mark = "☑" if picked else ("☐" if status == "ready" else "")
            self.tree.insert("", "end", iid=name, values=(mark, label, source, status), tags=(tag,))
        n = len(self.selected)
        self.count.configure(text=f"{n} selected")
        self.ok_btn.configure(text=f"Add {n} command{'s' if n != 1 else ''}")

    def on_click(self, event):
        name = self.tree.identify_row(event.y)
        if not name:
            return
        status = next(r[3] for r in self.rows if r[0] == name)
        if status != "ready":
            return "break"
        self.selected ^= {name}
        self.fill()
        self.tree.see(name)
        return "break"

    def select_none(self):
        self.selected.clear()
        self.fill()

    def ok(self):
        self.result = [(n, l) for n, l, s, st in self.rows if n in self.selected]
        self.destroy()

    def show(self):
        self.geometry("820x600")
        theme_place(self, self.master)
        self.grab_set()
        self.wait_window()
        return self.result


def theme_place(win, parent):
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_width()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_height()) // 3
    win.geometry(f"+{max(0, x)}+{max(0, y)}")