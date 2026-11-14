"""'Voice' tab of the editor: a synthesized voice shaped with sliders, or your own sound files."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np

from . import theme, voices
from .synth import MOODS, PARAMS

MOOD_LABELS = {"ack": "Acknowledged", "error": "Error", "unknown": "Not understood",
               "ready": "Ready", "chatter": "Chatter",
               "victory": "Victory", "scared": "Scared", "panic": "Panic", "sad": "Sad",
               "alarm": "Alarm", "greeting": "Greeting",
               "positive": "Positive answer", "negative": "Negative answer"}
FILE_COLUMNS = 4

GROUPS = [
    ("Pitch and tempo", ["pitch", "range", "speed", "syllable_ms", "gap_ms", "talk"]),
    ("Melody and mood", ["glide", "steady", "vib_rate", "vib_depth", "vib_share", "trill", "attitude"]),
    ("Timbre", ["brass", "harmonics", "ring", "grit", "noise", "body", "softness", "brightness",
                "space", "glitch"]),
]
PARAM_INFO = {p[0]: p for p in PARAMS}


class VoiceTab(ttk.Frame):
    def __init__(self, parent, sounds, voices_path, set_status):
        super().__init__(parent, padding=10)
        self.sounds = sounds
        self.path = voices_path
        self.set_status = set_status
        self.data = voices.load(voices_path)
        self.name = self.data["active"] if self.data["active"] in voices.names(self.data) \
            else voices.names(self.data)[0]
        self.working = voices.params(self.data, self.name)
        self.dirty = False
        self.vars, self.value_labels = {}, {}
        self._loading = False
        self.last_mood = "chatter"
        self.rng = np.random.default_rng()
        self._build()
        self.load_working()

    # ------------------------------------------------------------------ UI
    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Voice:").pack(side="left")
        self.voice_var = tk.StringVar(value=self.name)
        self.combo = ttk.Combobox(top, textvariable=self.voice_var, state="readonly", width=28,
                                  values=voices.names(self.data))
        self.combo.pack(side="left", padx=6)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.on_choose())
        ttk.Button(top, text="Save", style="Accent.TButton", command=self.save).pack(side="left", padx=(12, 0))
        ttk.Button(top, text="Save as…", command=self.save_as).pack(side="left", padx=4)
        ttk.Button(top, text="Revert", command=self.revert).pack(side="left")
        ttk.Button(top, text="Delete", command=self.delete).pack(side="left", padx=4)
        self.state_label = ttk.Label(top, text="", style="Hint.TLabel")
        self.state_label.pack(side="left", padx=12)

        src = ttk.Frame(self)
        src.pack(fill="x", pady=(10, 0))
        ttk.Label(src, text="Source:").pack(side="left")
        self.mode_var = tk.StringVar(value=voices.SYNTH)
        ttk.Radiobutton(src, text="Synthesized (sliders)", value=voices.SYNTH, variable=self.mode_var,
                        command=self.on_mode).pack(side="left", padx=(8, 16))
        ttk.Radiobutton(src, text="Sound files (your own recordings)", value=voices.FILES,
                        variable=self.mode_var, command=self.on_mode).pack(side="left")

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        # -- synthesized: slider groups
        self.synth_frame = ttk.Frame(self.body)
        grid = ttk.Frame(self.synth_frame)
        grid.pack(fill="both", expand=True)
        for col, (title, keys) in enumerate(GROUPS):
            box = ttk.LabelFrame(grid, text=title, padding=8)
            box.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))
            grid.columnconfigure(col, weight=1)
            for row, key in enumerate(keys):
                self._slider(box, row, key)
        grid.rowconfigure(0, weight=1)
        # -- sound files: one box per response type
        self.files_frame = ttk.Frame(self.body)
        intro = ttk.Label(self.files_frame, style="Hint.TLabel", wraplength=900, justify="left",
                          text="For each response, add one or more sound files (WAV, OGG, FLAC, MP3): the "
                               "droid plays one of them at random. When you save, the files are copied into "
                               "sounds/voices/<voice>/. A response with no files uses the synthesized voice.")
        intro.pack(fill="x", anchor="w")
        intro.bind("<Configure>", lambda e: intro.configure(wraplength=max(200, e.width - 10)))
        fgrid = ttk.Frame(self.files_frame)
        fgrid.pack(fill="both", expand=True, pady=(6, 0))
        self.lists = {}
        n = FILE_COLUMNS
        for i, mood in enumerate(MOODS):
            box = ttk.LabelFrame(fgrid, text=MOOD_LABELS[mood], padding=4)
            box.grid(row=i // n, column=i % n, sticky="nsew", padx=(0 if i % n == 0 else 6, 0),
                     pady=(0 if i < n else 6, 0))
            lb = tk.Listbox(box, height=5, activestyle="none", exportselection=False,
                            bg=theme.C["field"], fg=theme.C["text"], selectbackground=theme.C["select"],
                            selectforeground=theme.C["amber"], highlightthickness=1,
                            highlightbackground=theme.C["border"], highlightcolor=theme.C["amber"],
                            relief="flat", font=theme.C["F"]["body"])
            row = ttk.Frame(box)
            row.pack(side="bottom", fill="x", pady=(6, 0))     # buttons stay visible, the list shrinks
            lb.configure(height=2)
            lb.pack(fill="both", expand=True)
            lb.bind("<Double-1>", lambda e, m=mood: self.play_file(m))
            ttk.Button(row, text="▶", width=2, command=lambda m=mood: self.play_file(m)).pack(side="right")
            ttk.Button(row, text="Add…", width=5, command=lambda m=mood: self.add_files(m)).pack(side="left")
            ttk.Button(row, text="Remove", width=7,
                       command=lambda m=mood: self.remove_file(m)).pack(side="left", padx=4)
            self.lists[mood] = lb
        for c in range(n):
            fgrid.columnconfigure(c, weight=1)
        for r in range((len(MOODS) + n - 1) // n):
            fgrid.rowconfigure(r, weight=1)

        play = ttk.LabelFrame(self, text="Listen", padding=8)
        play.pack(side="bottom", fill="x", pady=(10, 0), before=self.body)   # always visible
        buttons = ttk.Frame(play)
        buttons.pack(fill="x")
        for mood in ("ack", "error", "unknown"):
            ttk.Button(buttons, text=f"▶ {MOOD_LABELS[mood]}",
                       command=lambda m=mood: self.play(m)).pack(side="left", padx=(0, 6))
        ttk.Label(buttons, text="Any response:").pack(side="left", padx=(12, 4))
        self.listen_var = tk.StringVar(value=MOOD_LABELS["victory"])
        pick = ttk.Combobox(buttons, textvariable=self.listen_var, state="readonly", width=14,
                            values=[MOOD_LABELS[m] for m in MOODS])
        pick.pack(side="left")
        pick.bind("<<ComboboxSelected>>", lambda e: self.play(self.listen_mood()))
        ttk.Button(buttons, text="▶", width=3, command=lambda: self.play(self.listen_mood())).pack(
            side="left", padx=(4, 0))
        self.mutate_btn = ttk.Button(buttons, text="🎲 Surprise me", command=self.mutate)
        self.mutate_btn.pack(side="left", padx=(16, 0))
        row2 = ttk.Frame(play)
        row2.pack(fill="x", pady=(8, 0))
        self.autoplay = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="Play when I release a slider",
                        variable=self.autoplay).pack(side="right")

        ttk.Label(row2, text="🔊 Master volume, microphone and audio output: Setup tab",
                  style="Hint.TLabel").pack(side="left")

    def _slider(self, box, row, key):
        """One compact row: name | slider | value."""
        _, label, lo, hi, res, desc = PARAM_INFO[key]
        name = ttk.Label(box, text=label, width=20)
        name.grid(row=row, column=0, sticky="w", pady=1)
        var = tk.DoubleVar()
        scale = ttk.Scale(box, from_=lo, to=hi, variable=var, orient="horizontal",
                          command=lambda _v, k=key: self.on_slide(k))
        scale.grid(row=row, column=1, sticky="ew", padx=6)
        val = ttk.Label(box, text="", width=6, anchor="e")
        val.grid(row=row, column=2, sticky="e")
        box.columnconfigure(1, weight=1)
        name.bind("<Enter>", lambda e, d=desc, l=label: self.set_status(f"{l}: {d}"))
        scale.bind("<ButtonRelease-1>", lambda e: self.autoplay.get() and self.play(self.last_mood))
        for w in (scale, val):
            w.bind("<Enter>", lambda e, d=desc, l=label: self.set_status(f"{l}: {d}"))
        self.vars[key] = var
        self.value_labels[key] = val

    # --------------------------------------------------------------- state
    @staticmethod
    def fmt(key, value):
        res = PARAM_INFO[key][4]
        return f"{value:.0f}" if res >= 1 else f"{value:.2f}"

    def load_working(self):
        self._loading = True
        for key, var in self.vars.items():
            var.set(self.working[key])
            self.value_labels[key].configure(text=self.fmt(key, self.working[key]))
        self.mode_var.set(self.working.get("mode", voices.SYNTH))
        self._loading = False
        self.show_mode()
        self.refresh_lists()
        self.update_state()

    # --------------------------------------------------------- sound files
    def show_mode(self):
        files = self.mode_var.get() == voices.FILES
        self.synth_frame.pack_forget()
        self.files_frame.pack_forget()
        (self.files_frame if files else self.synth_frame).pack(fill="both", expand=True)
        self.mutate_btn.state(["disabled"] if files else ["!disabled"])

    def on_mode(self):
        self.working["mode"] = self.mode_var.get()
        self.show_mode()
        self.mark_dirty()

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.update_state()

    def refresh_lists(self):
        files = self.working.get("files") or {}
        for mood, lb in self.lists.items():
            lb.delete(0, "end")
            for f in files.get(mood, []):
                name = os.path.basename(f)
                lb.insert("end", name if os.path.isfile(f) else f"⚠ missing: {name}")

    def add_files(self, mood):
        paths = filedialog.askopenfilenames(
            parent=self, title=f"Sound files for “{MOOD_LABELS[mood]}”",
            filetypes=[("Audio", " ".join("*" + e for e in voices.AUDIO_TYPES)), ("All files", "*.*")])
        if not paths:
            return
        self.working.setdefault("files", {}).setdefault(mood, []).extend(os.path.abspath(p) for p in paths)
        self.refresh_lists()
        self.mark_dirty()
        self.sounds.play(os.path.abspath(paths[0]))

    def remove_file(self, mood):
        sel = self.lists[mood].curselection()
        if not sel:
            return
        del self.working["files"][mood][sel[0]]
        self.refresh_lists()
        self.mark_dirty()

    def play_file(self, mood):
        sel = self.lists[mood].curselection()
        files = (self.working.get("files") or {}).get(mood, [])
        if sel and os.path.isfile(files[sel[0]]):
            self.sounds.play(files[sel[0]])
        else:
            self.play(mood)

    def update_state(self):
        kind = "built-in preset" if voices.is_builtin(self.name) else "your voice"
        if self.working.get("mode") == voices.FILES:
            n = sum(len(v) for v in (self.working.get("files") or {}).values())
            kind += f" · {n} sound file{'s' if n != 1 else ''}"
        mark = "● modified — " if self.dirty else ""
        active = " · used by Droid Commander" if self.data["active"] == self.name else ""
        self.state_label.configure(text=f"{mark}{kind}{active}")

    def on_slide(self, key):
        if self._loading:
            return
        res = PARAM_INFO[key][4]
        v = round(self.vars[key].get() / res) * res
        self.working[key] = v
        self.value_labels[key].configure(text=self.fmt(key, v))
        self.mark_dirty()

    def listen_mood(self):
        label = self.listen_var.get()
        return next((m for m, l in MOOD_LABELS.items() if l == label), "chatter")

    def play(self, mood):
        self.last_mood = mood
        self.sounds.play(mood, voice=dict(self.working))

    def mutate(self):
        """Random variation around the current settings."""
        for key, (_, _, lo, hi, res, _) in PARAM_INFO.items():
            v = self.working[key] + self.rng.normal(0, 0.15) * (hi - lo)
            self.working[key] = float(np.clip(round(v / res) * res, lo, hi))
        self.dirty = True
        self.load_working()
        self.play("chatter")

    def ask_discard(self):
        return not self.dirty or messagebox.askyesno(
            "Unsaved voice", f"Discard your changes to “{self.name}”?", parent=self)

    def persist(self, message):
        self.data["volume"] = voices.load(self.path).get("volume")   # set in the Setup tab
        voices.save(self.path, self.data)
        self.dirty = False
        self.combo.configure(values=voices.names(self.data))
        self.voice_var.set(self.name)
        self.update_state()
        self.set_status(message)

    # ------------------------------------------------------------- actions
    def on_choose(self):
        new = self.voice_var.get()
        if new == self.name:
            return
        if not self.ask_discard():
            self.voice_var.set(self.name)
            return
        self.name = new
        self.working = voices.params(self.data, new)
        self.dirty = False
        self.data["active"] = new
        self.load_working()
        self.persist(f"Droid Commander now speaks with “{new}”.")
        self.play("ack")

    def save(self):
        if voices.is_builtin(self.name):
            self.save_as()
            return
        self.working = voices.adopt_files(self.name, self.working)
        self.data["custom"][self.name] = dict(self.working)
        self.data["active"] = self.name
        self.refresh_lists()
        self.persist(f"Voice “{self.name}” saved and in use.")

    def save_as(self):
        suggestion = self.name if not voices.is_builtin(self.name) else f"My {self.name}"
        name = simpledialog.askstring("Save voice as", "Name for this voice:",
                                      initialvalue=suggestion, parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if voices.is_builtin(name):
            messagebox.showerror("Save voice", "That name belongs to a built-in preset.", parent=self)
            return
        if name in self.data["custom"] and name != self.name and not messagebox.askyesno(
                "Save voice", f"Replace your voice “{name}”?", parent=self):
            return
        self.working = voices.adopt_files(name, self.working)
        self.data["custom"][name] = dict(self.working)
        self.data["active"] = name
        self.name = name
        self.refresh_lists()
        self.persist(f"Voice “{name}” saved and in use.")

    def revert(self):
        self.working = voices.params(self.data, self.name)
        self.dirty = False
        self.load_working()

    def delete(self):
        if voices.is_builtin(self.name):
            messagebox.showinfo("Delete voice", "Built-in presets can't be deleted.", parent=self)
            return
        if not messagebox.askyesno("Delete voice", f"Delete your voice “{self.name}”?", parent=self):
            return
        del self.data["custom"][self.name]
        self.name = voices.names(self.data)[0]
        self.data["active"] = self.name
        self.working = voices.params(self.data, self.name)
        self.dirty = False
        self.load_working()
        self.persist(f"Voice deleted. Droid Commander now speaks with “{self.name}”.")
