"""'Events' tab: the game link (install/remove) and how the droid reacts to game events."""

import json
import os
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import gamelink, hud, theme
from .settings_io import update_settings
from .voice_editor import MOOD_LABELS


class EventsTab(ttk.Frame):
    def __init__(self, parent, editor):
        super().__init__(parent, padding=(14, 8))
        self.ed = editor
        self.dirty = False
        self._loading = True
        with open(editor.settings_path, "r", encoding="utf-8-sig") as f:
            s = json.load(f)
        self.cfg = gamelink.event_config(s)
        self.link_enabled = tk.BooleanVar(value=(s.get("game_link") or {}).get("enabled", True))
        self.manual_mod = (s.get("game_link") or {}).get("mod_dir") or None
        gamelink.MANUAL_MOD_DIR = self.manual_mod

        # ---- game link
        box = ttk.LabelFrame(self, text="Game link — how your commands reach the game, and how the droid knows what happens", padding=10)
        box.pack(fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.link_state = tk.Label(row, text="", bg=theme.C["bg"], font=theme.C["F"]["head"], anchor="w")
        self.link_state.pack(side="left")
        ttk.Button(row, text="Remove", command=self.remove).pack(side="right")
        self.install_btn = ttk.Button(row, text="Install game link", style="Accent.TButton", command=self.install)
        self.install_btn.pack(side="right", padx=6)
        ttk.Checkbutton(row, text="React to game events", variable=self.link_enabled,
                        command=self.mark_dirty).pack(side="right", padx=16)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Mod folder:").pack(side="left")
        self.mod_label = ttk.Label(row, text="", style="Hint.TLabel")
        self.mod_label.pack(side="left", padx=8)
        ttk.Button(row, text="Automatic", command=self.auto_mod).pack(side="right")
        ttk.Button(row, text="Choose folder…", command=self.choose_mod).pack(side="right", padx=6)
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(6, 0))
        self.hud_var = tk.BooleanVar(value=hud.enabled(s.get("game_link")))
        ttk.Checkbutton(row, text="Droid messages on the HUD", variable=self.hud_var,
                        command=self.save_hud_level).pack(side="left")
        ttk.Label(row, style="Hint.TLabel", text="answers, problems and game events, written like a translation "
                  "of the beeps in the droid's personality (Droid tab) — only on your screen"
                  ).pack(side="left", padx=10)
        self.link_info = ttk.Label(box, text="", style="Hint.TLabel", wraplength=1000, justify="left")
        self.link_info.pack(fill="x", anchor="w", pady=(6, 0))
        self.link_info.bind("<Configure>", lambda e: self.link_info.configure(wraplength=max(300, e.width - 10)))

        # ---- reactions table
        box = ttk.LabelFrame(self, text="Reactions — chance: how often the droid reacts · pause: seconds "
                                        "before it reacts to the same event again · your voice commands "
                                        "always come first", padding=(10, 6))
        box.pack(fill="both", expand=True, pady=(8, 0))
        heads = ("", "Event", "Droid response", "Chance", "Pause (s)", "")
        for c, h in enumerate(heads):
            tk.Label(box, text=h.upper(), bg=theme.C["bg"], fg=theme.C["cyan"], font=theme.C["F"]["sub"]).grid(
                row=0, column=c, sticky="w", padx=4, pady=(0, 4))
        box.columnconfigure(1, weight=1)
        responses = [MOOD_LABELS[m] for m in MOOD_LABELS]
        self.rows = {}
        for r, (key, (label, _)) in enumerate(gamelink.EVENTS.items(), start=1):
            c = self.cfg[key]
            on = tk.BooleanVar(value=c.get("enabled", True))
            resp = tk.StringVar(value=MOOD_LABELS.get(c["response"], c["response"]))
            chance = tk.StringVar(value=str(int(round(c.get("chance", 1.0) * 100))))  # %
            cool = tk.StringVar(value=f"{c.get('cooldown', 0):g}")
            ttk.Checkbutton(box, variable=on, command=self.mark_dirty).grid(row=r, column=0, padx=4)
            ttk.Label(box, text=label).grid(row=r, column=1, sticky="w", padx=4, pady=0)
            cb = ttk.Combobox(box, textvariable=resp, values=responses, state="readonly", width=15)
            cb.grid(row=r, column=2, padx=4, pady=0)
            cb.bind("<<ComboboxSelected>>", lambda e: self.mark_dirty())
            sp = ttk.Spinbox(box, from_=0, to=100, increment=10, textvariable=chance, width=5,
                             command=self.mark_dirty)
            sp.grid(row=r, column=3, padx=4)
            sp2 = ttk.Spinbox(box, from_=0, to=120, increment=1, textvariable=cool, width=5,
                              command=self.mark_dirty)
            sp2.grid(row=r, column=4, padx=4)
            for w in (sp, sp2):
                w.bind("<KeyRelease>", lambda e: self.mark_dirty())
            ttk.Button(box, text="▶", width=3, command=lambda v=resp: self.ed.sounds.play(self.code(v.get()))
                       ).grid(row=r, column=5, padx=4)
            self.rows[key] = (on, resp, chance, cool)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", pady=(8, 0), before=self.winfo_children()[0])
        self.state_label = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.state_label.pack(side="left")
        ttk.Button(bottom, text="Save", style="Accent.TButton", command=self.save).pack(side="right")
        ttk.Button(bottom, text="Defaults", command=self.defaults).pack(side="right", padx=6)
        self._loading = False
        self.refresh_link()
        self.after(3000, self.tick)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def code(label):
        return next((k for k, v in MOOD_LABELS.items() if v == label), label)

    def mark_dirty(self):
        if self._loading:
            return
        self.dirty = True
        self.state_label.configure(text="● unsaved changes")

    def mod_dir(self):
        return gamelink.mod_dir(self.ed.players_dir, self.manual_mod)

    def link_settings(self):
        return {"enabled": bool(self.link_enabled.get()), "mod_dir": self.manual_mod,
                "hud_messages": bool(self.hud_var.get())}

    def save_hud_level(self):
        """Saved right away: a running Droid Commander uses it at once."""
        with open(self.ed.settings_path, "r", encoding="utf-8-sig") as f:
            gl = dict(json.load(f).get("game_link") or {})
        gl["hud_messages"] = bool(self.hud_var.get())
        update_settings(self.ed.settings_path, {"game_link": gl})
        self.ed.set_status("Droid messages on the HUD: " + ("on." if self.hud_var.get() else "off."))

    def save_mod_choice(self):
        with open(self.ed.settings_path, "r", encoding="utf-8-sig") as f:
            gl = dict(json.load(f).get("game_link") or {})
        gl.update(self.link_settings())
        update_settings(self.ed.settings_path, {"game_link": gl})
        gamelink.MANUAL_MOD_DIR = self.manual_mod
        self.ed.on_game_folder_changed()           # the game's controls come from this mod
        self.refresh_link()

    def choose_mod(self):
        from tkinter import filedialog
        start = self.mod_dir() or os.path.expanduser("~")
        path = filedialog.askdirectory(parent=self, initialdir=start, mustexist=True,
                                       title="Fate of the Galaxy mod folder (the one with the 'data' folder)")
        if not path:
            return
        mod = gamelink.valid_mod_dir(path)
        if not mod:
            messagebox.showerror("Mod folder", "That folder has no 'data' folder inside.\n\nChoose the mod's "
                                 "own folder, e.g. …/Library/FotG_2/FotG_2-2.0.2.", parent=self)
            return
        self.manual_mod = mod
        self.save_mod_choice()
        self.ed.set_status(f"Mod folder set: {mod}")

    def auto_mod(self):
        self.manual_mod = None
        self.save_mod_choice()
        self.ed.set_status("Mod folder: found automatically.")

    def refresh_link(self):
        C = theme.C
        mod = self.mod_dir()
        self.mod_label.configure(
            text=(mod or "not found") + ("   (chosen by hand)" if self.manual_mod else "   (found automatically)"))
        if not mod:
            self.link_state.configure(text="⚠  Fate of the Galaxy not found", fg=C["warn"])
            self.link_info.configure(text="Press “Choose folder…” and pick the mod folder (the one with the "
                                          "'data' folder inside, e.g. …/Library/FotG_2/FotG_2-2.0.2).")
            self.install_btn.configure(text="Install game link")
            return
        st = gamelink.script_status(mod)
        name = os.path.basename(mod)
        text, color = {"installed": (f"✓  Installed in {name}", C["ok"]),
                       "outdated": (f"⚠  Installed in {name}, but outdated — install again", C["warn"]),
                       "missing": (f"○  Not installed in {name}", C["dim"])}[st]
        if st == "installed" and gamelink.outdated_in_game(self.ed.players_dir):
            text, color = ("⚠  The game is still running the old game link — restart FreeSpace Open",
                           C["warn"])
        self.link_state.configure(text=text, fg=color)
        self.install_btn.configure(text="Update game link" if st == "outdated" else "Install game link")
        info = ("Adds one small script to the mod (data/tables/lua/" + gamelink.SCRIPT_NAME + "). "
                "It is how your voice commands reach the game: it presses their game controls from "
                "inside the game, as if you pressed their key, and tells Droid Commander what happens "
                "in the game. FreeSpace Open loads it when it starts. ")
        info += ("In multiplayer it runs in fair-play mode: the droid only knows what your HUD shows "
                 "(“enemies left” counts only ships on your radar). ")
        ev = gamelink.find_event_file(self.ed.players_dir)
        if ev:
            age = time.time() - os.path.getmtime(ev)
            when = "just now" if age < 60 else f"{int(age // 60)} min ago" if age < 3600 else \
                time.strftime("%d/%m %H:%M", time.localtime(os.path.getmtime(ev)))
            info += f"Last game event received {when}."
        elif st == "installed":
            info += "No game events yet: start a mission (restart the game if it was already running)."
        info += "  Note: Fate of the Galaxy's own in-cockpit droid also squeals when your hull is hit."
        self.link_info.configure(text=info)

    def tick(self):
        if self.winfo_exists():
            self.refresh_link()
            self.after(3000, self.tick)

    def install(self):
        mod = self.mod_dir()
        if not mod:
            return
        try:
            gamelink.install(mod)
        except OSError as e:
            messagebox.showerror("Game link", f"Can't install the script:\n{e}", parent=self)
            return
        self.refresh_link()
        self.ed.set_status("Game link installed. If FreeSpace Open is running, close and restart it: "
                           "it loads scripts only when it starts.")

    def remove(self):
        mod = self.mod_dir()
        if not mod or gamelink.script_status(mod) == "missing":
            return
        if not messagebox.askyesno("Game link", "Remove the game link script from the mod?", parent=self):
            return
        gamelink.uninstall(mod)
        self.refresh_link()
        self.ed.set_status("Game link removed.")

    def defaults(self):
        self._loading = True
        for key, (_, d) in gamelink.EVENTS.items():
            on, resp, chance, cool = self.rows[key]
            on.set(True)
            resp.set(MOOD_LABELS.get(d["response"], d["response"]))
            chance.set(str(int(d["chance"] * 100)))
            cool.set(f"{d['cooldown']:g}")
        self._loading = False
        self.mark_dirty()

    def collect(self):
        events = {}
        for key, (on, resp, chance, cool) in self.rows.items():
            try:
                ch = min(100, max(0, float(chance.get() or 0))) / 100
                cd = max(0.0, float(cool.get() or 0))
            except ValueError:
                raise ValueError(f"“{gamelink.EVENTS[key][0]}”: chance and pause must be numbers")
            events[key] = {"enabled": bool(on.get()), "response": self.code(resp.get()),
                           "chance": round(ch, 2), "cooldown": cd}
        return events

    def save(self):
        try:
            events = self.collect()
        except ValueError as e:
            messagebox.showerror("Events", str(e), parent=self)
            return False
        update_settings(self.ed.settings_path, {"events": events,
                                                "game_link": self.link_settings()})
        self.dirty = False
        self.state_label.configure(text="")
        self.ed.set_status("Event reactions saved. A running Droid Commander uses them right away.")
        return True
