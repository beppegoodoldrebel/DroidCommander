"""Commands tab helpers: choose the game's control preset, and import game actions as commands."""

import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import theme
from .bindings import list_pilots, list_presets, pilot_preset, preset_path
from .phrases import normalize
from .settings_io import update_settings


def title_from_bind(bind):
    """'TARGET_NEXT_CLOSEST_HOSTILE' -> 'Target Next Closest Hostile'"""
    return " ".join(w.capitalize() for w in bind.split("_"))


def phrase_from_label(label):
    """'Engage Hyperdrive (End Mission)' -> 'engage hyperdrive'"""
    t = re.sub(r"\(.*?\)", " ", label).replace("&", " and ")
    return normalize(re.sub(r"[-_/]", " ", t))


class GameControlsPanel(ttk.LabelFrame):
    """Pick which FreeSpace Open control preset the commands use."""

    def __init__(self, parent, editor):
        super().__init__(parent, text="Game controls — the keys are read from this preset", padding=8)
        self.ed = editor
        b = editor.bindings
        self.players_dir = b.players_dir
        self.mode = tk.StringVar(value="pilot" if b.follow_pilot else "fixed")
        self.pilot_var = tk.StringVar(value=b.pilot or "")
        self.preset_var = tk.StringVar(value=os.path.splitext(os.path.basename(b.fixed_path))[0])

        row = ttk.Frame(self)
        row.pack(fill="x")
        ttk.Label(row, text="Players folder:").pack(side="left")
        self.dir_label = tk.Label(row, text="", bg=theme.C["bg"], fg=theme.C["cyan"],
                                  font=theme.C["F"]["mono"], anchor="w")
        self.dir_label.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row, text="Browse…", command=self.browse).pack(side="right")

        row = ttk.Frame(self)
        row.pack(fill="x", pady=(6, 0))
        ttk.Radiobutton(row, text="Follow pilot", value="pilot", variable=self.mode,
                        command=self.apply).pack(side="left")
        self.pilot_combo = ttk.Combobox(row, textvariable=self.pilot_var, state="readonly", width=18)
        self.pilot_combo.pack(side="left", padx=(6, 18))
        self.pilot_combo.bind("<<ComboboxSelected>>", lambda e: (self.mode.set("pilot"), self.apply()))
        ttk.Radiobutton(row, text="Fixed preset", value="fixed", variable=self.mode,
                        command=self.apply).pack(side="left")
        self.preset_combo = ttk.Combobox(row, textvariable=self.preset_var, state="readonly", width=20)
        self.preset_combo.pack(side="left", padx=6)
        self.preset_combo.bind("<<ComboboxSelected>>", lambda e: (self.mode.set("fixed"), self.apply()))
        self.info = ttk.Label(row, text="", style="Hint.TLabel")
        self.info.pack(side="left", padx=(14, 0))
        self.fill_lists()
        self.refresh_status()

    # ------------------------------------------------------------------ UI
    def fill_lists(self):
        d = self.players_dir
        self.dir_label.configure(text=d if len(d) < 90 else "…" + d[-88:])
        self.pilots = list_pilots(d)
        self.pilot_combo.configure(values=[p for p, _ in self.pilots])
        if self.pilots and self.pilot_var.get() not in [p for p, _ in self.pilots]:
            self.pilot_var.set(self.pilots[0][0])
        self.preset_combo.configure(values=list_presets(d))

    def refresh_status(self):
        b = self.ed.bindings
        if not b.raw:
            self.info.configure(text="⚠ No game controls yet: press Browse… and choose FreeSpace Open's "
                                     "data\\players folder", style="Warn.TLabel")
            return
        text = f"Using {b.preset_name} · {b.usable_count()} actions usable by voice"
        style = "Ok.TLabel"
        if self.mode.get() == "pilot":
            if b.follow_pilot and pilot_preset(b.players_dir, b.pilot):
                text += f" · follows {b.pilot} in game"
            else:
                text += " · ⚠ pilot preset not found, using the fixed preset"
                style = "Warn.TLabel"
        else:
            for p, pr in self.pilots:
                if pr and pr != b.preset_name:
                    text += f" · ⚠ pilot {p} uses {pr} in game"
                    style = "Warn.TLabel"
                    break
        self.info.configure(text=text, style=style)

    def browse(self):
        d = filedialog.askdirectory(parent=self, title="FreeSpace Open players folder (data/players)",
                                    initialdir=self.players_dir or os.getcwd())
        if not d:
            return
        d = os.path.normpath(d)
        if os.path.basename(d).lower() == "presets":
            d = os.path.dirname(d)
        if not list_presets(d) and not list_pilots(d):
            messagebox.showerror("Game controls", "No pilots or presets found there.\nChoose the "
                                 "folder …\\FreeSpaceOpen\\data\\players.", parent=self)
            return
        self.players_dir = d
        self.fill_lists()
        presets = list_presets(d)
        if presets and self.preset_var.get() not in presets:
            self.preset_var.set(presets[0])
        self.apply()

    def apply(self):
        d = self.players_dir
        follow = self.mode.get() == "pilot" and bool(self.pilot_var.get())
        fixed = self.preset_var.get()
        fixed_file = preset_path(d, fixed) if fixed else self.ed.bindings.fixed_path
        try:
            self.ed.bindings.configure(fixed_file, d, self.pilot_var.get() or None, follow)
        except (OSError, ValueError) as e:
            messagebox.showerror("Game controls", f"Can't read the preset:\n{e}", parent=self)
            return
        update_settings(self.ed.settings_path, {
            "bindings_file": os.path.abspath(fixed_file), "fso_players_dir": d,
            "pilot": self.pilot_var.get() or None, "follow_pilot": follow})
        self.refresh_status()
        self.ed.on_bindings_changed()
        self.ed.set_status(f"Game controls: {self.ed.bindings.preset_name}. "
                           "A running Droid Commander switches right away.")


class ImportDialog(tk.Toplevel):
    """Tick game actions from the preset to turn them into voice commands."""

    def __init__(self, parent, editor):
        super().__init__(parent)
        self.configure(bg=theme.C["bg"])
        self.title("Import commands from the game")
        self.transient(parent)
        self.ed = editor
        self.result = None
        self.selected = set()
        used = {a.get("bind") for c in editor.commands for a in c.get("actions", [])}
        b = editor.bindings
        self.rows = []
        for bind in b.raw:
            if bind.endswith("_AXIS"):
                continue
            label = editor.labels.get(bind) or title_from_bind(bind)
            r = b.resolve(bind)
            if bind in used:
                status = "already a command"
            elif r:
                status = "ready"
            else:
                status = "joystick only" if "JOY" in b.describe(bind) else "not bound"
            self.rows.append((bind, label, r.describe() if r else b.describe(bind), status))
        self.rows.sort(key=lambda x: (x[3] != "ready", x[1].lower()))

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"Actions in {b.preset_name}. Click to tick the ones you want as voice "
                            "commands; each gets a phrase from its name, which you can edit later.",
                  style="Hint.TLabel", wraplength=760).pack(anchor="w")
        top = ttk.Frame(frm)
        top.pack(fill="x", pady=8)
        ttk.Label(top, text="Search:").pack(side="left")
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.fill())
        ttk.Entry(top, textvariable=self.filter, width=30).pack(side="left", padx=6)
        ttk.Button(top, text="Select all ready", command=self.select_all).pack(side="left", padx=(12, 4))
        ttk.Button(top, text="Select none", command=self.select_none).pack(side="left")
        bottom = ttk.Frame(frm)
        bottom.pack(side="bottom", fill="x", pady=(10, 0))   # always visible
        tf = ttk.Frame(frm)
        tf.pack(fill="both", expand=True)
        cols = ("sel", "label", "key", "status")
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=12, selectmode="none")
        for c, text, w, anchor in (("sel", "", 40, "center"), ("label", "Game action", 320, "w"),
                                   ("key", "Bound to", 230, "w"), ("status", "Status", 150, "w")):
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
        for bind, label, key, status in self.rows:
            if f and f not in label.lower() and f not in bind.lower():
                continue
            picked = bind in self.selected
            tag = "picked" if picked else ("ready" if status == "ready" else "off")
            mark = "☑" if picked else ("☐" if status == "ready" else "")
            self.tree.insert("", "end", iid=bind, values=(mark, label, key, status), tags=(tag,))
        n = len(self.selected)
        self.count.configure(text=f"{n} selected")
        self.ok_btn.configure(text=f"Add {n} command{'s' if n != 1 else ''}")

    def on_click(self, event):
        bind = self.tree.identify_row(event.y)
        if not bind:
            return
        status = next(r[3] for r in self.rows if r[0] == bind)
        if status != "ready":
            return "break"
        self.selected ^= {bind}
        self.fill()
        self.tree.see(bind)
        return "break"

    def select_all(self):
        f = self.filter.get().lower().strip()
        self.selected |= {b for b, l, k, s in self.rows
                          if s == "ready" and (not f or f in l.lower() or f in b.lower())}
        self.fill()

    def select_none(self):
        self.selected.clear()
        self.fill()

    def ok(self):
        self.result = [(b, l) for b, l, k, s in self.rows if b in self.selected]
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
