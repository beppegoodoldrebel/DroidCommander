"""Graphical editor for config/commands.json (tkinter, no extra dependencies)."""

import copy
import ctypes
import json
import os
import queue
import re
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import gamelink
from .controls import Catalog
from .paths import resolve_model
from .executor import CommandError, Executor, check_command
from .luacmd import LuaControls
from .phrases import DROID, PhraseBook, command_call, missing_words, normalize
from .sounds import AUDIO_EXT, SoundBank
from .voice_editor import MOOD_LABELS, VoiceTab
from .droid_tab import DroidTab
from .events_tab import EventsTab
from .setup_tab import SetupTab
from .squad import DEFAULT_WING_NAMES, is_squad_order, wing_label
from .game_controls import ImportDialog, phrases_from_label
from .gamelink import QUESTIONS
from .settings_io import update_settings
from . import theme

DEFAULT_MOODS = ["ack", "error", "unknown", "ready", "chatter"]
CONFIGURE_SUBTITLE = "Astromech control interface · configure"
ACTIVE_SUBTITLE = "Active · listening for your orders"
KEY_ORDER = ["name", "enabled", "phrases", "actions", "sound"]
ACTION_TYPES = [("bind", "Game control"), ("wait", "Wait"), ("ask", "Question")]
TYPE_LABEL = dict(ACTION_TYPES)


# ----------------------------------------------------------------- helpers
def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def action_type(action):
    return next((t for t, _ in ACTION_TYPES if t in action), None)


def format_commands(data):
    """Pretty JSON: one block per command, short values kept on one line."""
    def ordered(cmd):
        keys = [k for k in KEY_ORDER if k in cmd] + [k for k in cmd if k not in KEY_ORDER]
        return [(k, cmd[k]) for k in keys]

    blocks = []
    for cmd in data["commands"]:
        fields = [f"            {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}"
                  for k, v in ordered(cmd)]
        blocks.append("        {\n" + ",\n".join(fields) + "\n        }")
    out = '{\n    "commands": [\n' + ",\n".join(blocks) + "\n    ]"
    for k, v in data.items():
        if k != "commands":
            out += f",\n    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}"
    return out + "\n}\n"


def place_near(win, parent):
    win.update_idletasks()
    x = parent.winfo_rootx() + (parent.winfo_width() - win.winfo_reqwidth()) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - win.winfo_reqheight()) // 3
    win.geometry(f"+{max(0, x)}+{max(0, y)}")


class Modal(tk.Toplevel):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.parent = parent
        self.result = None
        self.title(title)
        self.configure(bg=theme.C["bg"])
        self.transient(parent)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def show(self):
        theme.polish(self)
        place_near(self, self.parent)
        self.grab_set()
        self.wait_window()
        return self.result


# ---------------------------------------------------------------- dialogs
class BindPicker(Modal):
    """Choose one of the game's controls (named as the mod names them)."""

    def __init__(self, parent, editor, current=""):
        super().__init__(parent, "Choose a game control")
        self.resizable(True, True)
        self.editor = editor
        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.fill())
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Search:").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(frm, textvariable=self.filter, width=40)
        entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        cols = ("label", "bind", "input", "status")
        self.tree = ttk.Treeview(frm, columns=cols, show="headings", height=18, selectmode="browse")
        for c, text, w in (("label", "Game control", 260), ("bind", "FSO name", 250),
                           ("input", "Named by", 150), ("status", "Status", 120)):
            self.tree.heading(c, text=text)
            self.tree.column(c, width=w, anchor="w")
        self.tree.tag_configure("bad", foreground=theme.C["off"])
        sb = ttk.Scrollbar(frm, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=8)
        sb.grid(row=1, column=2, sticky="ns", pady=8)
        frm.columnconfigure(1, weight=1)
        frm.rowconfigure(1, weight=1)
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=3, sticky="e")
        ttk.Button(btns, text="OK", command=self.ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left")
        self.tree.bind("<Double-1>", lambda e: self.ok())
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.current = current
        self.fill()
        entry.focus_set()

    def fill(self):
        f = self.filter.get().lower().strip()
        cat = self.editor.catalog
        self.tree.delete(*self.tree.get_children())
        rows = []
        for bind in cat.names():
            label = cat.label(bind)
            if f and f not in bind.lower() and f not in label.lower():
                continue
            ok = not cat.disabled(bind)
            rows.append((label, bind, "Fate of the Galaxy" if cat.from_mod(bind) else "FreeSpace Open",
                         "OK" if ok else "off in this mod", ok))
        for label, bind, inp, status, ok in sorted(rows, key=lambda r: (r[2] != "Fate of the Galaxy",
                                                                         r[0].lower())):
            self.tree.insert("", "end", iid=bind, values=(label, bind, inp, status),
                             tags=() if ok else ("bad",))
        if self.current and self.tree.exists(self.current):
            self.tree.selection_set(self.current)
            self.tree.see(self.current)

    def ok(self):
        sel = self.tree.selection()
        if sel:
            self.result = sel[0]
            self.destroy()


class ActionDialog(Modal):
    """Create or edit one action of a command."""

    def __init__(self, parent, editor, action=None):
        super().__init__(parent, "Edit action" if action else "Add action")
        self.editor = editor
        a = dict(action or {"bind": ""})
        self.type = tk.StringVar(value=action_type(a) or "bind")
        self.bind_var = tk.StringVar(value=a.get("bind", ""))
        self.wait_var = tk.StringVar(value=str(a.get("wait", 200)))
        self.ask_var = tk.StringVar(value=QUESTIONS.get(a.get("ask", "status"), QUESTIONS["status"])[0])
        self.repeat_var = tk.StringVar(value=str(a.get("repeat", 1)))
        self.info = tk.StringVar()

        frm = ttk.Frame(self, padding=12)
        frm.pack(fill="both", expand=True)
        types = ttk.Frame(frm)
        types.pack(anchor="w")
        for t, label in ACTION_TYPES:
            ttk.Radiobutton(types, text=label, value=t, variable=self.type,
                            command=self.on_type).pack(side="left", padx=(0, 12))

        self.box = ttk.Frame(frm, padding=(0, 10))
        self.box.pack(fill="x")
        self.frames = {}
        f = self.frames["bind"] = ttk.Frame(self.box)
        self.bind_label = tk.StringVar()
        ttk.Entry(f, textvariable=self.bind_label, state="readonly", width=44).pack(side="left")
        ttk.Button(f, text="Choose…", command=self.choose_bind).pack(side="left", padx=6)
        f = self.frames["wait"] = ttk.Frame(self.box)
        ttk.Spinbox(f, from_=10, to=10000, increment=50, textvariable=self.wait_var,
                    width=8).pack(side="left")
        ttk.Label(f, text="milliseconds").pack(side="left", padx=6)
        f = self.frames["ask"] = ttk.Frame(self.box)
        ttk.Combobox(f, textvariable=self.ask_var, values=[q[0] for q in QUESTIONS.values()],
                     state="readonly", width=46).pack(side="left")

        self.opts = ttk.Frame(frm)
        self.opts.pack(fill="x")
        ttk.Label(self.opts, text="Repeat:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(self.opts, from_=1, to=50, textvariable=self.repeat_var, width=6).grid(
            row=0, column=1, sticky="w", padx=6)
        ttk.Label(self.opts, text="times").grid(row=0, column=2, sticky="w")

        ttk.Label(frm, textvariable=self.info, style="Hint.TLabel", wraplength=420).pack(
            anchor="w", pady=(10, 0))
        btns = ttk.Frame(frm)
        btns.pack(anchor="e", pady=(10, 0))
        ttk.Button(btns, text="OK", command=self.ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left")
        self.bind("<Escape>", lambda e: self.destroy())
        self.on_type()
        if action is None:
            self.after(80, self.choose_bind)

    def on_type(self):
        for t, f in self.frames.items():
            f.pack_forget()
        self.frames[self.type.get()].pack(anchor="w")
        if self.type.get() in ("wait", "ask"):
            self.opts.pack_forget()
        else:
            self.opts.pack(fill="x", after=self.box)
        self.update_info()

    def update_info(self):
        t = self.type.get()
        e = self.editor
        if t == "bind":
            b = self.bind_var.get()
            self.bind_label.set(e.bind_title(b) if b else "")
            if not b:
                self.info.set("Choose the game control to press.")
            elif e.catalog.disabled(b):
                self.info.set("⚠ This control is switched off in the installed mod: it does nothing.")
            else:
                self.info.set("The game link presses this control inside the game, as if you pressed "
                              "its key (whatever key, joystick button or none it has).")
        elif t == "ask":
            self.info.set("The droid answers with a positive or negative sound, judged on your ship's "
                          "state (needs the game link, Events tab). No key is pressed.")
        else:
            self.info.set("Pauses before the next action.")

    def choose_bind(self):
        if self.type.get() != "bind":
            return
        r = BindPicker(self, self.editor, self.bind_var.get()).show()
        self.grab_set()
        if r:
            self.bind_var.set(r)
            self.update_info()

    def ok(self):
        t = self.type.get()
        try:
            if t == "bind":
                if not self.bind_var.get():
                    raise ValueError("choose a game control")
                action = {"bind": self.bind_var.get()}
            elif t == "ask":
                q = next(k for k, v in QUESTIONS.items() if v[0] == self.ask_var.get())
                self.result = {"ask": q}
                self.destroy()
                return
            else:
                ms = int(self.wait_var.get())
                if ms <= 0:
                    raise ValueError("the wait must be positive")
                self.result = {"wait": ms}
                self.destroy()
                return
            repeat = int(self.repeat_var.get() or 1)
            if repeat < 1:
                raise ValueError("repeat must be at least 1")
            if repeat > 1:
                action["repeat"] = repeat
        except ValueError as ex:
            messagebox.showerror("Invalid action", str(ex), parent=self)
            return
        self.result = action
        self.destroy()


# ----------------------------------------------------------------- editor
class Editor:
    def __init__(self, root, settings_path, commands_path):
        self.root = root
        self.settings_path = settings_path
        self.commands_path = commands_path
        self.settings = load_json(settings_path)
        self.first_run_note = None
        self.first_run_setup()
        gamelink.MANUAL_MOD_DIR = (self.settings.get("game_link") or {}).get("mod_dir") or None
        self.players_dir = gamelink.game_players_dir(self.settings)
        self.catalog = Catalog(self.mod_dir())
        self.executor = Executor(LuaControls(lambda: self.players_dir))
        snd = self.settings.get("sound", {})
        self.sound_folder = snd.get("folder", "sounds")
        self.voices_path = snd.get("voices_file", "config/voices.json")
        self.sounds = SoundBank(self.sound_folder, snd.get("volume", 0.8),
                                snd.get("output_device"), snd.get("backend", "winsound"),
                                self.voices_path)
        self.model_path = resolve_model(self.settings.get("model_path", "models/vosk-model-small-en-us-0.15"))
        self.wake_words = self.settings["droid"]["wake_words"]
        self.callsigns = self.settings.get("callsigns") or {}
        self.wing_names = self.settings.get("wing_names", DEFAULT_WING_NAMES)
        self.droid_name = self.settings["droid"].get("name", "R2")
        self.try_info_default = f"e.g. “{self.settings['droid'].get('name', 'R2')}, open S-foils”"
        self.fuzzy = self.settings.get("recognition", {}).get("fuzzy_match", 0.75)
        self.vocab = {}                 # word -> known by the speech model
        self._vocab_running = False
        self._vocab_after = None
        self.current = None
        self.dirty = False
        self._loading = False
        self._suppress_select = False
        self._backup_done = False
        self._load_file()
        self._build()
        theme.polish(self.root)
        self.refresh_list()
        if self.commands:
            self.select(0)
        self.root.after(300, self.run_vocab)
        if self.first_run_note:
            self.tabbar.select(3)               # Events tab: install the game link / choose the mod
            self.root.after(1500, lambda: self.set_status(self.first_run_note))
        self.root.after(800, self.check_controls_changed)

    def first_run_setup(self):
        """No game folder known yet: look for FreeSpace Open and point to the game link."""
        s = self.settings
        if s.get("fso_players_dir") or (s.get("game_link") or {}).get("mod_dir"):
            return
        players = gamelink.detect_players_dir()
        if players:
            update_settings(self.settings_path, {"fso_players_dir": players})
            s["fso_players_dir"] = players
            self.first_run_note = ("Welcome! Found FreeSpace Open. Now install the game link (Events tab): "
                                   "your commands are pressed inside the game through it.")
        else:
            self.first_run_note = ("Welcome! FreeSpace Open was not found automatically: in the Events tab, "
                                   "press “Choose folder…” and pick the Fate of the Galaxy mod folder.")

    def mod_dir(self):
        """The mod folder (chosen in the Events tab, or found automatically)."""
        return gamelink.mod_dir(self.players_dir, gamelink.MANUAL_MOD_DIR)

    def on_game_folder_changed(self):
        """The Events tab chose another mod folder: reload the game's controls."""
        self.players_dir = gamelink.game_players_dir(load_json(self.settings_path))
        self.catalog = Catalog(self.mod_dir())
        self.update_rows()
        if self.current is not None:
            self.refresh_actions(select=self.selected_action())
        self.check_controls_changed()

    def check_controls_changed(self):
        from .controls_watch import check_controls
        check_controls(self)

    # ------------------------------------------------------------- data
    def _load_file(self):
        data = load_json(self.commands_path)
        self.commands = data.get("commands", [])
        self.extra = {k: v for k, v in data.items() if k != "commands"}

    def bind_title(self, bind):
        return f"{self.catalog.label(bind)}  ({bind})"

    def cmd(self):
        return self.commands[self.current] if self.current is not None else None

    def call_of(self, c):
        return command_call(c, self.callsigns)

    def owner_key(self, c, phrase):
        """Phrases only clash between commands addressed to the same callsign."""
        return self.call_of(c), normalize(phrase)

    def phrase_owners(self):
        owners = {}
        for i, c in enumerate(self.commands):
            if not c.get("enabled", True):
                continue
            for p in c.get("phrases", []):
                n = normalize(p)
                if n:
                    owners.setdefault(self.owner_key(c, p), set()).add(i)
        return owners

    def unknown_words(self, cmd):
        words = {w for p in cmd.get("phrases", []) for w in normalize(p).split()}
        return sorted(w for w in words if self.vocab.get(w) is False)

    def problems(self, idx, owners=None):
        c = self.commands[idx]
        out = []
        if not c.get("phrases"):
            out.append("no phrases")
        try:
            check_command(c)
        except CommandError as e:
            out.append(str(e))
        off = [a["bind"] for a in c.get("actions", []) if "bind" in a and self.catalog.disabled(a["bind"])]
        if off:
            out.append("switched off in the installed mod: " + ", ".join(self.catalog.label(b) for b in off))
        unknown = self.unknown_words(c)
        if unknown:
            out.append("words unknown to the speech model: " + ", ".join(unknown))
        owners = owners if owners is not None else self.phrase_owners()
        for p in c.get("phrases", []):
            others = owners.get(self.owner_key(c, p), set()) - {idx}
            if others and c.get("enabled", True):
                names = ", ".join(self.commands[o]["name"] for o in sorted(others))
                out.append(f"'{p}' is also used by {names}")
        return out

    def summary(self, c):
        """What the command does in the game, e.g. 'Toggle S-foils' or 'Increase Engine ×6'."""
        try:
            check_command(c)
        except CommandError:
            return "⚠"
        parts = []
        for a in c.get("actions", []):
            if "bind" in a:
                n = int(a.get("repeat", 1))
                parts.append(self.catalog.label(a["bind"]) + (f" ×{n}" if n > 1 else ""))
        if not parts:
            return "? question" if any("ask" in a for a in c.get("actions", [])) else ""
        return " + ".join(parts)

    # --------------------------------------------------------------- UI
    def _build(self):
        r = self.root
        r.geometry("1220x800")
        r.minsize(960, 620)
        self.C = C = theme.apply(r)

        bar, rule = theme.header(r, "Droid Commander", CONFIGURE_SUBTITLE)
        bar.pack(fill="x")
        rule.pack(fill="x", padx=12)
        self.header = bar
        self.launch_btn = ttk.Button(bar, text="▶  LAUNCH!", style="Launch.TButton", command=self.launch)
        self.launch_btn.pack(side="right", padx=16, pady=8)
        self.runtime = None
        self.status_bar = status = tk.Frame(r, bg=C["panel"])
        status.pack(side="bottom", fill="x")
        tk.Label(status, text="▌", bg=C["panel"], fg=C["amber"], font=C["F"]["head"]).pack(side="left", padx=(8, 2))
        self.status = tk.Label(status, text="SYSTEMS NOMINAL", bg=C["panel"], fg=C["cyan"],
                               font=C["F"]["mono"], anchor="w")
        self.status.pack(side="left", fill="x", pady=4)
        self.workspace = ws = tk.Frame(r, bg=C["bg"])        # CONFIGURE mode: tabs + pages
        ws.pack(fill="both", expand=True)
        notebook = ttk.Notebook(ws, style="Tabless.TNotebook")
        self.tabbar = tabs = theme.TabBar(ws, notebook)
        tabs.pack_bar(padx=12, pady=(10, 0))
        notebook.pack(fill="both", expand=True, padx=8, pady=(6, 6))
        self.droid_tab = DroidTab(notebook, self.settings_path, self.model_path, self.set_status,
                                  self.on_droid_saved)
        tabs.add(self.droid_tab, "Droid", "◉")
        cmd_tab = ttk.Frame(notebook)
        tabs.add(cmd_tab, "Commands", "☰")
        self.voice_tab = VoiceTab(notebook, self.sounds, self.voices_path, self.set_status)
        tabs.add(self.voice_tab, "Voice", "♪")
        self.events_tab = EventsTab(notebook, self)
        tabs.add(self.events_tab, "Events", "⚡")
        self.setup_tab = SetupTab(notebook, self)
        tabs.add(self.setup_tab, "Setup", "⚙")
        tabs.select(0)
        r.bind("<Control-Tab>", lambda e: tabs.step(1))
        r.bind("<Control-Shift-Tab>", lambda e: tabs.step(-1))
        r.bind("<Control-ISO_Left_Tab>", lambda e: tabs.step(-1))

        paned = ttk.PanedWindow(cmd_tab, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=(8, 0))
        left = ttk.Frame(paned)
        right = ttk.Frame(paned, padding=(12, 0, 0, 0))
        paned.add(left, weight=2)
        paned.add(right, weight=3)

        # ---- left: command list
        top = ttk.Frame(left)
        top.pack(fill="x")
        ttk.Label(top, text="Search:").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh_list())
        ttk.Entry(top, textvariable=self.search).pack(side="left", fill="x", expand=True, padx=(6, 0))
        lf = ttk.Frame(left)
        lf.pack(fill="both", expand=True, pady=6)
        self.cmd_tree = ttk.Treeview(lf, columns=("name", "to", "keys"), show="headings", selectmode="browse")
        self.cmd_tree.heading("name", text="Command")
        self.cmd_tree.heading("to", text="To")
        self.cmd_tree.heading("keys", text="Game control")
        self.cmd_tree.column("name", width=220)
        self.cmd_tree.column("to", width=70)
        self.cmd_tree.column("keys", width=170)
        self.cmd_tree.tag_configure("warn", foreground=C["warn"])
        self.cmd_tree.tag_configure("off", foreground=C["off"])
        sb = ttk.Scrollbar(lf, orient="vertical", command=self.cmd_tree.yview)
        self.cmd_tree.configure(yscrollcommand=sb.set)
        self.cmd_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.cmd_tree.bind("<<TreeviewSelect>>", self.on_select)
        lb = ttk.Frame(left)
        lb.pack(fill="x")
        ttk.Button(lb, text="New", command=self.new_command).pack(side="left")
        ttk.Button(lb, text="Duplicate", command=self.duplicate_command).pack(side="left", padx=4)
        ttk.Button(lb, text="Delete", command=self.delete_command).pack(side="left")
        ttk.Button(lb, text="⇩ Import from game…", style="Accent.TButton",
                   command=self.import_from_game).pack(side="right")

        # ---- right: details
        box = ttk.LabelFrame(right, text="Command", padding=8)
        box.pack(fill="x")
        ttk.Label(box, text="Name:").pack(side="left")
        self.name_var = tk.StringVar()
        self.name_var.trace_add("write", lambda *_: self.on_name())
        self.name_entry = ttk.Entry(box, textvariable=self.name_var)
        self.name_entry.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Label(box, text="To:").pack(side="left", padx=(6, 0))
        self.call_var = tk.StringVar()
        self.call_combo = ttk.Combobox(box, textvariable=self.call_var, state="readonly", width=14)
        self.call_combo.pack(side="left", padx=(6, 10))
        self.call_combo.bind("<<ComboboxSelected>>", lambda e: self.on_call())
        self.refresh_call_choices()
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(box, text="Enabled", variable=self.enabled_var,
                        command=self.on_enabled).pack(side="left")

        box = ttk.LabelFrame(right, text="Phrases — one per line, without the name you call", padding=8)
        box.pack(fill="both", expand=True, pady=(8, 0))
        tf = ttk.Frame(box)
        tf.pack(fill="both", expand=True)
        self.phrases = tk.Text(tf, height=4, wrap="none", undo=True)
        theme.style_text(self.phrases)
        psb = ttk.Scrollbar(tf, orient="vertical", command=self.phrases.yview)
        self.phrases.configure(yscrollcommand=psb.set)
        self.phrases.pack(side="left", fill="both", expand=True)
        psb.pack(side="left", fill="y")
        self.phrases.bind("<<Modified>>", self.on_phrases)
        self.phrase_info = ttk.Label(box, text="", wraplength=620, justify="left")
        self.phrase_info.pack(anchor="w", pady=(6, 0))

        box = ttk.LabelFrame(right, text="Actions — performed in order", padding=8)
        box.pack(fill="both", expand=True, pady=(8, 0))
        af = ttk.Frame(box)
        af.pack(fill="both", expand=True)
        cols = ("type", "value", "result", "repeat")
        self.act_tree = ttk.Treeview(af, columns=cols, show="headings", height=3, selectmode="browse")
        for c, text, w in (("type", "Type", 100), ("value", "Action", 260), ("result", "FSO name", 210),
                           ("repeat", "Repeat", 60)):
            self.act_tree.heading(c, text=text)
            self.act_tree.column(c, width=w, anchor="w")
        self.act_tree.tag_configure("warn", foreground=C["warn"])
        self.act_tree.pack(side="left", fill="both", expand=True)
        self.act_tree.bind("<Double-1>", lambda e: self.edit_action())
        ab = ttk.Frame(box)
        ab.pack(fill="x", pady=(6, 0))
        ttk.Button(ab, text="Add…", command=self.add_action).pack(side="left")
        ttk.Button(ab, text="Edit…", command=self.edit_action).pack(side="left", padx=4)
        ttk.Button(ab, text="Remove", command=self.remove_action).pack(side="left")
        ttk.Button(ab, text="▲", width=3, command=lambda: self.move_action(-1)).pack(side="left", padx=(12, 2))
        ttk.Button(ab, text="▼", width=3, command=lambda: self.move_action(1)).pack(side="left")

        box = ttk.LabelFrame(right, text="Droid response and test", padding=8)
        box.pack(fill="x", pady=(8, 0))
        ttk.Label(box, text="Response:").pack(side="left")
        self.sound_var = tk.StringVar()
        self.sound_var.trace_add("write", lambda *_: self.on_sound())
        self.sound_combo = ttk.Combobox(box, textvariable=self.sound_var, width=18, state="readonly")
        self.sound_combo.pack(side="left", padx=6)
        ttk.Button(box, text="▶ Play", command=lambda: self.sounds.play(self.response_code())).pack(
            side="left", padx=4)
        ttk.Label(box, text="sounds come from the Voice tab", style="Hint.TLabel").pack(side="left", padx=6)
        self.test_btn = ttk.Button(box, text="Test in game", command=self.test_command)
        self.test_btn.pack(side="right")
        self.test_info = ttk.Label(box, text="", style="Hint.TLabel")
        self.test_info.pack(side="right", padx=8)

        # ---- bottom: phrase tester + status
        bottom = ttk.Frame(cmd_tab, padding=(4, 8))
        bottom.pack(side="bottom", fill="x", before=paned)   # always visible
        ttk.Label(bottom, text="Try a phrase:").pack(side="left")
        self.try_var = tk.StringVar()
        self.try_var.trace_add("write", lambda *_: self.on_try())
        ttk.Entry(bottom, textvariable=self.try_var, width=40).pack(side="left", padx=6)
        self.try_info = ttk.Label(bottom, text=self.try_info_default, style="Hint.TLabel")
        self.try_info.pack(side="left")
        ttk.Button(bottom, text="Save", style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Button(bottom, text="Reload", command=self.reload).pack(side="right", padx=6)
        ttk.Button(bottom, text="▶ Test all in game…", command=self.test_all).pack(side="right", padx=(0, 12))

        r.bind("<Control-s>", lambda e: self.save())
        r.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_title()
        self.refresh_sound_choices()

    # ------------------------------------------------------- list ops
    def row_values(self, i, owners):
        c = self.commands[i]
        probs = self.problems(i, owners)
        name = ("⚠ " if probs else "") + (c.get("name") or "(no name)")
        tags = ("off",) if not c.get("enabled", True) else ("warn",) if probs else ()
        return (name, self.call_label(self.call_of(c)), self.summary(c)), tags

    def refresh_list(self):
        f = self.search.get().lower().strip()
        owners = self.phrase_owners()
        self._suppress_select = True
        self.cmd_tree.delete(*self.cmd_tree.get_children())
        for i, c in enumerate(self.commands):
            text = (c.get("name", "") + " " + " ".join(c.get("phrases", []))).lower()
            if f and f not in text:
                continue
            values, tags = self.row_values(i, owners)
            self.cmd_tree.insert("", "end", iid=str(i), values=values, tags=tags)
        if self.current is not None and self.cmd_tree.exists(str(self.current)):
            self.cmd_tree.selection_set(str(self.current))
            self.cmd_tree.see(str(self.current))
        self.root.after_idle(lambda: setattr(self, "_suppress_select", False))

    def update_rows(self):
        owners = self.phrase_owners()
        for iid in self.cmd_tree.get_children():
            values, tags = self.row_values(int(iid), owners)
            self.cmd_tree.item(iid, values=values, tags=tags)

    def select(self, idx):
        self.current = idx
        self.load_current()
        if self.cmd_tree.exists(str(idx)):
            self._suppress_select = True
            self.cmd_tree.selection_set(str(idx))
            self.cmd_tree.see(str(idx))
            self.root.after_idle(lambda: setattr(self, "_suppress_select", False))

    def on_select(self, _event):
        if self._suppress_select:
            return
        sel = self.cmd_tree.selection()
        if sel:
            self.current = int(sel[0])
            self.load_current()

    def load_current(self):
        c = self.cmd()
        self._loading = True
        self.name_var.set(c.get("name", "") if c else "")
        self.enabled_var.set(c.get("enabled", True) if c else True)
        self.phrases.delete("1.0", "end")
        if c:
            self.phrases.insert("1.0", "\n".join(c.get("phrases", [])))
        self.phrases.edit_reset()
        self.phrases.edit_modified(False)
        self.refresh_sound_choices()
        self.sound_var.set(self.response_label(c.get("sound", "ack")) if c else "")
        self.call_var.set(self.call_label(self.call_of(c)) if c else "")
        self._loading = False
        self.refresh_actions()
        self.update_phrase_info()
        self.test_info.configure(text="")

    def changed(self, rows=True):
        self.dirty = True
        self.update_title()
        if rows:
            self.update_rows()

    def update_title(self):
        if getattr(self, "runtime", None) is not None:
            return
        self.root.title(f"{'● ' if self.dirty else ''}Droid Commander — configure")

    def set_status(self, text):
        if not text and getattr(self, "runtime", None) is not None:
            text = "DROID COMMANDER RUNNING — CONFIGURATION LOCKED"
        self.status.configure(text=text or "SYSTEMS NOMINAL")

    def new_command(self):
        self.commands.append({"name": "New command", "phrases": [], "actions": [], "sound": "ack"})
        self.search.set("")
        self.current = len(self.commands) - 1
        self.refresh_list()
        self.select(self.current)
        self.changed()
        self.name_entry.focus_set()
        self.name_entry.select_range(0, "end")

    def duplicate_command(self):
        c = self.cmd()
        if not c:
            return
        dup = copy.deepcopy(c)
        dup["name"] = c.get("name", "") + " (copy)"
        self.commands.insert(self.current + 1, dup)
        self.current += 1
        self.refresh_list()
        self.select(self.current)
        self.changed()

    def delete_command(self):
        c = self.cmd()
        if not c or not messagebox.askyesno("Delete command", f"Delete “{c.get('name')}”?", parent=self.root):
            return
        del self.commands[self.current]
        self.current = min(self.current, len(self.commands) - 1) if self.commands else None
        self.refresh_list()
        if self.current is not None:
            self.select(self.current)
        else:
            self.load_current()
        self.changed()

    # ------------------------------------------------------ field ops
    def on_name(self):
        if self._loading or self.cmd() is None:
            return
        self.cmd()["name"] = self.name_var.get()
        self.changed()

    def call_label(self, call):
        """'Droid' is shown as the droid's own name (e.g. 'R2')."""
        return self.droid_name if call == DROID else call

    def refresh_call_choices(self):
        self.call_combo.configure(values=[self.droid_name] + list(self.callsigns))

    def on_call(self):
        c = self.cmd()
        if c is None:
            return
        label = self.call_var.get()
        if label in self.callsigns:
            c["call"] = label
        else:
            c.pop("call", None)
        self.changed()
        self.update_phrase_info()
        self.on_try()

    def on_enabled(self):
        c = self.cmd()
        if c is None:
            return
        if self.enabled_var.get():
            c.pop("enabled", None)
        else:
            c["enabled"] = False
        self.changed()
        self.update_phrase_info()

    def on_phrases(self, _event):
        if not self.phrases.edit_modified():
            return
        self.phrases.edit_modified(False)
        if self._loading or self.cmd() is None:
            return
        lines = [l.strip() for l in self.phrases.get("1.0", "end").splitlines() if l.strip()]
        self.cmd()["phrases"] = lines
        self.changed()
        self.update_phrase_info()
        if self._vocab_after:
            self.root.after_cancel(self._vocab_after)
        self._vocab_after = self.root.after(800, self.run_vocab)

    def update_phrase_info(self):
        c = self.cmd()
        if c is None:
            self.phrase_info.configure(text="", style="Hint.TLabel")
            return
        msgs = []
        unknown = self.unknown_words(c)
        if unknown:
            msgs.append(f"⚠ The speech model doesn't know: {', '.join(unknown)}. Use other words "
                        "(e.g. “wing men” instead of “wingmen”).")
        owners = self.phrase_owners()
        for p in c.get("phrases", []):
            others = owners.get(self.owner_key(c, p), set()) - {self.current}
            if others and c.get("enabled", True):
                msgs.append(f"⚠ “{p}” is also used by: "
                            + ", ".join(self.commands[o]["name"] for o in sorted(others)))
        if msgs:
            self.phrase_info.configure(text="\n".join(msgs), style="Warn.TLabel")
            return
        words = {w for p in c.get("phrases", []) for w in normalize(p).split()}
        if not words:
            self.phrase_info.configure(text="Add at least one phrase.", style="Hint.TLabel")
        elif any(w not in self.vocab for w in words) and os.path.isdir(self.model_path):
            self.phrase_info.configure(text="Checking words against the speech model…", style="Hint.TLabel")
        else:
            self.phrase_info.configure(text="✓ All words are known to the speech model.", style="Ok.TLabel")

    def refresh_sound_choices(self):
        values = list(MOOD_LABELS.values())
        c = self.cmd()
        if c and c.get("sound") and c["sound"] not in MOOD_LABELS:    # legacy file path / custom
            values.append(c["sound"])
        self.sound_combo.configure(values=values)

    def response_label(self, code):
        return MOOD_LABELS.get(code, code)

    def response_code(self):
        label = self.sound_var.get()
        return next((k for k, v in MOOD_LABELS.items() if v == label), label) or "ack"

    def on_sound(self):
        c = self.cmd()
        if self._loading or c is None:
            return
        code = self.response_code()
        if code == "ack":
            c.pop("sound", None)              # ack is the default
        else:
            c["sound"] = code
        self.changed(rows=False)

    # ----------------------------------------------------- action ops
    def describe_action(self, a):
        t = action_type(a)
        result, warn = "", False
        if t == "bind":
            value = self.catalog.label(a["bind"])
            result = a["bind"]
            if not self.catalog.known(a["bind"]):
                result, warn = "⚠ not a FreeSpace Open control", True
            elif self.catalog.disabled(a["bind"]):
                result, warn = "⚠ switched off in this mod", True
        elif "key" in a or "mouse" in a:
            value, result, warn = a.get("key") or a.get("mouse"), "⚠ keys aren't used any more", True
        elif t == "wait":
            value = f"{a['wait']} ms"
        elif t == "ask":
            value = QUESTIONS.get(a["ask"], (a["ask"],))[0]
            result = "answers ±"
        else:
            value, warn = json.dumps(a), True
        repeat = "" if t in ("wait", "ask") else str(a.get("repeat", 1))
        return (TYPE_LABEL.get(t, "Old key action"), value, result, repeat), warn

    def refresh_actions(self, select=None):
        self.act_tree.delete(*self.act_tree.get_children())
        c = self.cmd()
        if not c:
            return
        for i, a in enumerate(c.get("actions", [])):
            values, warn = self.describe_action(a)
            self.act_tree.insert("", "end", iid=str(i), values=values, tags=("warn",) if warn else ())
        if select is not None and self.act_tree.exists(str(select)):
            self.act_tree.selection_set(str(select))

    def selected_action(self):
        sel = self.act_tree.selection()
        return int(sel[0]) if sel else None

    def add_action(self):
        c = self.cmd()
        if c is None:
            return
        a = ActionDialog(self.root, self).show()
        if a:
            c.setdefault("actions", []).append(a)
            self.refresh_actions(select=len(c["actions"]) - 1)
            self.changed()

    def edit_action(self):
        c, i = self.cmd(), self.selected_action()
        if c is None or i is None:
            return
        a = ActionDialog(self.root, self, c["actions"][i]).show()
        if a:
            c["actions"][i] = a
            self.refresh_actions(select=i)
            self.changed()

    def remove_action(self):
        c, i = self.cmd(), self.selected_action()
        if c is None or i is None:
            return
        del c["actions"][i]
        self.refresh_actions(select=min(i, len(c["actions"]) - 1))
        self.changed()

    def move_action(self, delta):
        c, i = self.cmd(), self.selected_action()
        if c is None or i is None:
            return
        j = i + delta
        acts = c["actions"]
        if 0 <= j < len(acts):
            acts[i], acts[j] = acts[j], acts[i]
            self.refresh_actions(select=j)
            self.changed()

    # ------------------------------------------------------ test / try
    def test_all(self):
        from .test_all import TestAllDialog
        TestAllDialog(self)

    def test_command(self):
        c = self.cmd()
        if c is None:
            return
        cmd = copy.deepcopy(c)
        try:
            check_command(cmd)
        except CommandError as e:
            messagebox.showerror("Can't test", str(e), parent=self.root)
            return
        if any("ask" in a for a in cmd.get("actions", [])):
            messagebox.showinfo("Test", "A question presses nothing: ask it by voice during a mission.",
                                parent=self.root)
            return
        self.test_btn.state(["disabled"])
        outcome = queue.Queue()

        def run():    # background thread: never touch tkinter here
            try:
                if is_squad_order(cmd):                       # wingman order: to all fighters
                    from .squad import SQUAD_SHORTCUTS
                    shortcut = next(a["bind"] for a in cmd["actions"] if a.get("bind") in SQUAD_SHORTCUTS)
                    ok, note = self.executor.lua.send_order(shortcut, None)
                    if not ok:
                        raise CommandError(note)
                else:
                    self.executor.execute(cmd)
                outcome.put(("✓ Done in game", "Ok.TLabel", cmd.get("sound", "ack")))
            except CommandError as e:
                outcome.put((f"⚠ {e}", "Warn.TLabel", "error"))

        def poll():
            try:
                msg, style, sound = outcome.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            self.sounds.play(sound)
            self.test_info.configure(text=msg, style=style)
            self.test_btn.state(["!disabled"])

        def start():
            threading.Thread(target=run, daemon=True).start()
            self.root.after(100, poll)

        def tick(n):
            if n > 0:
                self.test_info.configure(text=f"Switch to the game… {n}", style="Hint.TLabel")
                self.root.after(1000, tick, n - 1)
            else:
                start()

        tick(5)

    def on_try(self):
        text = self.try_var.get().strip()
        if not text:
            self.try_info.configure(text=self.try_info_default, style="Hint.TLabel")
            return
        book = PhraseBook(self.commands, self.wake_words, fuzzy=self.fuzzy, callsigns=self.callsigns,
                          wing_names=self.wing_names)
        cmd, group, rest, score = book.match_full(text)
        had_wake = group is not None
        if cmd is None:
            self.try_info.configure(text="→ not understood", style="Warn.TLabel")
            return
        note = "" if had_wake else "   (no name called: works only with push-to-talk)"
        who = wing_label(group) if group in book.wing_forms else self.call_label(self.call_of(cmd))
        if is_squad_order(cmd):
            note += ("   then picks " + (wing_label(group) if group in book.wing_forms else "All Ships")
                     + " in the comm menu")
        self.try_info.configure(text=f"→ {who}: {cmd['name']}  (match {score:.2f}){note}", style="Ok.TLabel")

    # ------------------------------------------------------ vocabulary
    def run_vocab(self):
        self._vocab_after = None
        if self._vocab_running or not os.path.isdir(self.model_path):
            return
        words = {w for c in self.commands for p in c.get("phrases", []) for w in normalize(p).split()}
        words |= {w for ww in self.wake_words for w in normalize(ww).split()}
        words |= {w for forms in self.callsigns.values() for f in forms for w in normalize(f).split()}
        todo = sorted(w for w in words if w not in self.vocab and w != "[unk]")
        if not todo:
            return
        self._vocab_running = True
        self.set_status("Checking words against the speech model…")

        results = queue.Queue()

        def work():   # background thread: never touch tkinter here
            try:
                missing = set(missing_words(self.model_path, todo))
                results.put(({w: w not in missing for w in todo}, None))
            except Exception as e:
                results.put(({}, e))

        def poll():
            try:
                result, error = results.get_nowait()
            except queue.Empty:
                self.root.after(100, poll)
                return
            if error:
                self.set_status(f"Vocabulary check failed: {error}")
            self._vocab_done(result)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(100, poll)

    def _vocab_done(self, result):
        self.vocab.update(result)
        self._vocab_running = False
        self.update_rows()
        self.update_phrase_info()
        if result:
            self.set_status("")
        self.run_vocab()   # words typed meanwhile

    # ------------------------------------------------------- save etc.
    def save(self):
        for c in self.commands:
            if not c.get("name", "").strip():
                messagebox.showerror("Can't save", "Every command needs a name.", parent=self.root)
                return
        text = format_commands({"commands": self.commands, **self.extra})
        if not self._backup_done and os.path.exists(self.commands_path):
            shutil.copy2(self.commands_path, self.commands_path + ".bak")
            self._backup_done = True
        tmp = self.commands_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self.commands_path)
        self.dirty = False
        self.update_title()
        owners = self.phrase_owners()
        warn = sum(1 for i in range(len(self.commands)) if self.problems(i, owners))
        note = f" {warn} command(s) have warnings (⚠)." if warn else ""
        self.set_status(f"Saved. A running Droid Commander reloads it automatically.{note}")

    def reload(self):
        if self.dirty and not messagebox.askyesno(
                "Reload", "Discard your unsaved changes and reload from disk?", parent=self.root):
            return
        self.catalog = Catalog(self.mod_dir())
        self._load_file()
        self.current = 0 if self.commands else None
        self.dirty = False
        self.update_title()
        self.refresh_list()
        self.load_current()
        self.refresh_sound_choices()
        self.run_vocab()
        self.set_status("Reloaded from disk.")

    def add_control_commands(self, picked):
        """Add one command per (control, label), with phrases made from the label."""
        names = {c.get("name") for c in self.commands}
        first = len(self.commands)
        for bind, label in picked:
            name, k = label, 2
            while name in names:
                name, k = f"{label} ({k})", k + 1
            names.add(name)
            self.commands.append({"name": name, "phrases": phrases_from_label(label),
                                  "actions": [{"bind": bind}], "sound": "ack"})
        self.search.set("")
        self.current = first
        self.refresh_list()
        self.select(first)
        self.changed()
        self.run_vocab()

    def import_from_game(self):
        picked = ImportDialog(self.root, self).show()
        if not picked:
            return
        self.add_control_commands(picked)
        self.set_status(f"Added {len(picked)} command(s). Check their phrases, then Save.")

    def on_droid_saved(self, name, wake_words, callsigns=None, wing_names=None):
        self.wake_words = wake_words
        self.droid_name = name
        if callsigns is not None:
            self.callsigns = callsigns
        if wing_names is not None:
            self.wing_names = wing_names
        self.refresh_call_choices()
        if self.cmd() is not None:
            self.call_var.set(self.call_label(self.call_of(self.cmd())))
        self.update_rows()
        self.run_vocab()
        self.try_info_default = f"e.g. “{name}, open S-foils”"
        self.on_try()

    # ------------------------------------------------------- ACTIVE mode
    def launch(self):
        """Switch to ACTIVE mode: start Droid Commander and show its status in this window."""
        if self.runtime is not None:
            self.stop_runtime()
            return
        unsaved = [n for n, d in (("commands", self.dirty), ("droid name", self.droid_tab.dirty),
                                  ("voice", self.voice_tab.dirty), ("events", self.events_tab.dirty),
                                  ("setup", self.setup_tab.dirty)) if d]
        if unsaved:
            ans = messagebox.askyesnocancel(
                "Launch", f"You have unsaved changes ({', '.join(unsaved)}).\n\n"
                          "Save them before launching? (No = launch with the last saved version)",
                parent=self.root)
            if ans is None:
                return
            if ans:
                if self.dirty:
                    self.save()
                if self.droid_tab.dirty and not self.droid_tab.save():
                    return
                if self.voice_tab.dirty:
                    self.voice_tab.save()
                if self.events_tab.dirty and not self.events_tab.save():
                    return
                if self.setup_tab.dirty and not self.setup_tab.save():
                    return
                if self.dirty or self.droid_tab.dirty or self.voice_tab.dirty or self.events_tab.dirty:
                    return                      # a save was cancelled
        self.setup_tab.stop_meter()
        from .runtime_window import RuntimePanel
        self.workspace.pack_forget()
        self.status_bar.pack_forget()
        try:
            self.runtime = RuntimePanel(self.root, os.path.abspath(self.settings_path),
                                        os.path.abspath(self.commands_path), self.on_runtime_stopped)
        except OSError as e:
            self.show_configure()
            messagebox.showerror("Launch", f"Can't start Droid Commander:\n{e}", parent=self.root)
            return
        self.runtime.pack(fill="both", expand=True)
        self.launch_btn.configure(text="■  STOP · CONFIGURE")
        self.header.subtitle.configure(text=ACTIVE_SUBTITLE.upper())
        self.root.title("Droid Commander — active")

    def stop_runtime(self):
        if self.runtime is not None and self.runtime.winfo_exists():
            self.runtime.stop()                 # calls on_runtime_stopped
        else:
            self.on_runtime_stopped()

    def on_runtime_stopped(self):
        self.runtime = None
        self.show_configure()
        self.set_status("Droid Commander stopped. You can edit the configuration.")

    def show_configure(self):
        """Back to CONFIGURE mode (tabs)."""
        self.status_bar.pack(side="bottom", fill="x")
        self.workspace.pack(fill="both", expand=True)
        self.launch_btn.configure(text="▶  LAUNCH!")
        self.header.subtitle.configure(text=CONFIGURE_SUBTITLE.upper())
        self.update_title()

    def on_close(self):
        mode = "active" if self.runtime is not None else "configure"
        if self.runtime is not None:
            if not messagebox.askyesno("Droid Commander is running",
                                       "Stop Droid Commander and quit?\n\n"
                                       "Next time the app opens, it will start listening right away.",
                                       parent=self.root):
                return
            self.stop_runtime()
        try:                                    # reopen in the same mode next time
            update_settings(self.settings_path, {"ui_mode": mode})
        except (OSError, ValueError):
            pass
        if self.setup_tab.dirty:
            ans = messagebox.askyesnocancel("Unsaved setup", "Save the Setup tab before closing?",
                                            parent=self.root)
            if ans is None:
                return
            if ans and not self.setup_tab.save():
                return
        self.setup_tab.stop_meter()
        if self.events_tab.dirty:
            ans = messagebox.askyesnocancel("Unsaved events", "Save the event reactions before closing?",
                                            parent=self.root)
            if ans is None or (ans and not self.events_tab.save()):
                return
        if self.droid_tab.dirty:
            ans = messagebox.askyesnocancel("Unsaved droid name", "Save the droid name before closing?",
                                            parent=self.root)
            if ans is None or (ans and not self.droid_tab.save()):
                return
        if self.voice_tab.dirty and not messagebox.askyesno(
                "Unsaved voice", "Your voice changes are not saved. Close anyway?", parent=self.root):
            return
        if self.dirty:
            ans = messagebox.askyesnocancel("Unsaved changes", "Save your changes before closing?",
                                            parent=self.root)
            if ans is None:
                return
            if ans:
                self.save()
                if self.dirty:
                    return
        self.root.destroy()


def run_editor(settings_path, commands_path, mode=None):
    """The Droid Commander app: CONFIGURE (tabs) and ACTIVE (listening) in one window.

    mode: "configure", "active", or None = the mode the app was in when last closed.
    """
    try:  # crisp text on high-DPI screens
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    ed = Editor(root, settings_path, commands_path)
    if mode is None:
        mode = ed.settings.get("ui_mode", "configure")
    if mode == "active":
        root.after(300, ed.launch)
    root.mainloop()
