"""'Droid' tab of the editor: the droid's name, i.e. the wake word that commands start with."""

import json
import os
import queue
import re
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import hud, theme
from .phrases import missing_words, normalize
from .settings_io import update_settings
from .squad import DEFAULT_WING_NAMES

# How the speech model often hears single letters and some numbers
LETTER_SOUNDS = {"r": ["are"], "b": ["bee"], "c": ["see"], "d": ["dee"], "g": ["gee"], "i": ["eye"],
                 "j": ["jay"], "k": ["kay"], "o": ["oh"], "q": ["queue"], "t": ["tee"], "u": ["you"],
                 "v": ["vee"], "y": ["why"], "z": ["zee"]}
NUMBER_SOUNDS = {"two": ["to"], "four": ["for"]}


def name_variants(name, limit=8):
    """'R2' -> ['r two', 'r to', 'are two', 'are to']: the ways the recognizer may hear it."""
    tokens = []
    for tok in normalize(name).split():
        # spelled-out initials ("bb", "cr") are said letter by letter
        if len(tok) <= 3 and not re.search(r"[aeiou]", tok):
            tokens += list(tok)
        else:
            tokens.append(tok)
    if not tokens:
        return []
    combos = [[]]
    for tok in tokens:
        options = [tok] + LETTER_SOUNDS.get(tok, []) + NUMBER_SOUNDS.get(tok, [])
        combos = [c + [o] for c in combos for o in options]
    out = []
    for c in combos:
        s = " ".join(c)
        if s not in out:
            out.append(s)
    return out[:limit]


def format_callsigns(callsigns):
    return "\n".join(f"{name}: {', '.join(forms)}" for name, forms in callsigns.items())


def parse_callsigns(text):
    """'Wingmen: wing men, squadron' lines -> {'Wingmen': ['wing men', 'squadron']}"""
    out = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, forms = line.split(":", 1)
        name = name.strip()
        forms = [normalize(f) for f in forms.split(",") if normalize(f)]
        if name and forms and name.lower() != "droid":
            out[name] = list(dict.fromkeys(forms))
    return out


def save_droid_settings(path, name, wake_words, **extra):
    """Update the droid block (name, wake words, personality…), keeping the rest of the file."""
    with open(path, "r", encoding="utf-8-sig") as f:
        droid = dict(json.load(f).get("droid") or {})
    droid.update(name=name, wake_words=wake_words, **extra)
    update_settings(path, {"droid": droid})


class DroidTab(ttk.Frame):
    def __init__(self, parent, settings_path, model_path, set_status, on_saved):
        super().__init__(parent, padding=(14, 8))
        self.path = settings_path
        self.model_path = model_path
        self.set_status = set_status
        self.on_saved = on_saved
        with open(settings_path, "r", encoding="utf-8-sig") as f:
            s = json.load(f)
        droid = s.get("droid", {})
        self.dirty = False
        self._loading = True
        self._vocab = {}
        self._vocab_after = None
        self._vocab_running = False
        self.auto = True      # renaming rebuilds the variants (until you edit them by hand)

        box = ttk.LabelFrame(self, text="Droid name and personality", padding=(10, 6))
        box.pack(fill="x")
        left = ttk.Frame(box)
        left.pack(side="left", fill="y", anchor="n")
        self.name_var = tk.StringVar(value=droid.get("name", "R2"))
        self.name_var.trace_add("write", lambda *_: self.on_name())
        entry = ttk.Entry(left, textvariable=self.name_var, font=theme.C["F"]["big"], width=18)
        entry.pack(anchor="w")
        ttk.Label(left, style="Hint.TLabel", wraplength=330, justify="left",
                  text="Voice commands only run when they start with this name, "
                       "e.g. “Chopper, open S-foils”. Write it the way you say it: "
                       "“R2”, “BB-8”, “Chopper”.").pack(anchor="w", pady=(6, 0))

        # personality: how the droid writes its answers on the HUD (independent of its voice)
        right = ttk.Frame(box)
        right.pack(side="left", fill="both", expand=True, padx=(24, 0), anchor="n")
        self.personalities = hud.load_personalities()
        self.pers_keys = hud.personality_labels(self.personalities)
        row = ttk.Frame(right)
        row.pack(fill="x")
        ttk.Label(row, text="Personality:").pack(side="left")
        current = droid.get("personality") or hud.DEFAULT_PERSONALITY
        self.pers_var = tk.StringVar(value=next((l for k, l in self.pers_keys if k == current),
                                                self.pers_keys[0][1] if self.pers_keys else ""))
        cb = ttk.Combobox(row, textvariable=self.pers_var, state="readonly", width=16,
                          values=[l for _, l in self.pers_keys])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: (self.mark_dirty(), self.show_example()))
        ttk.Label(row, text="Calls you:").pack(side="left", padx=(12, 0))
        self.you_var = tk.StringVar(value=droid.get("call_player") or "")
        self.you_var.trace_add("write", lambda *_: (None if self._loading else (self.mark_dirty(),
                                                                              self.show_example())))
        ttk.Entry(row, textvariable=self.you_var, width=14).pack(side="left", padx=6)
        self.captions_var = tk.BooleanVar(value=droid.get("beep_captions", True))
        ttk.Checkbutton(row, text="Beep captions", variable=self.captions_var,
                        command=lambda: (self.mark_dirty(), self.show_example())).pack(side="left", padx=(8, 0))
        row = ttk.Frame(right)
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="Example", command=self.show_example).pack(side="left")
        self.example = ttk.Label(row, text="", wraplength=470, justify="left", foreground=theme.C["cyan"])
        self.example.pack(side="left", padx=8)
        ttk.Label(right, style="Hint.TLabel", wraplength=780, justify="left",
                  text="How the droid writes on the HUD (Setup tab). “Calls you”: e.g. Boss, Commander. "
                       "Lines: config/personalities.json — edit them or add your own personality."
                  ).pack(anchor="w", pady=(4, 0))

        box = ttk.LabelFrame(self, text="Recognized as — one per line", padding=10)
        box.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.variants = tk.Text(row, height=4, width=34, undo=True)
        theme.style_text(self.variants)
        self.variants.pack(side="left")
        self.variants.insert("1.0", "\n".join(droid.get("wake_words", [])))
        self.variants.edit_modified(False)
        self.variants.bind("<<Modified>>", self.on_variants)
        side = ttk.Frame(row)
        side.pack(side="left", fill="y", padx=12)
        ttk.Button(side, text="Rebuild from name", command=self.rebuild).pack(anchor="w")
        ttk.Label(side, style="Hint.TLabel", wraplength=640, justify="left",
                  text="The speech model often hears letters as words (“R” as “are”), so the "
                       "name is accepted in each of these forms. They are rebuilt automatically "
                       "when you change the name, unless you edit them by hand.").pack(anchor="w", pady=(8, 0))
        self.vocab_info = ttk.Label(box, text="", wraplength=700, justify="left")
        self.vocab_info.pack(anchor="w", pady=(8, 0))

        box = ttk.LabelFrame(self, text="Other callsigns — who else you can give orders to", padding=10)
        box.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.calls = tk.Text(row, height=2, width=60, undo=True)
        theme.style_text(self.calls)
        self.calls.pack(side="left")
        self.calls.insert("1.0", format_callsigns(s.get("callsigns") or {}))
        self.calls.edit_modified(False)
        self.calls.bind("<<Modified>>", self.on_calls_or_wings)
        ttk.Label(row, style="Hint.TLabel", wraplength=330, justify="left",
                  text="One per line: Name: spoken forms, comma separated. In the Commands tab, set a "
                       "command's “To:” to one of these names, e.g. “Wingmen, attack my target”."
                  ).pack(side="left", padx=12, anchor="n")

        box = ttk.LabelFrame(self, text="Wing names — orders to one wing: “Squad Alpha, cover me”", padding=10)
        box.pack(fill="x", pady=(6, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.wings = tk.Text(row, height=3, width=60, undo=True, wrap="word")
        theme.style_text(self.wings)
        self.wings.pack(side="left")
        self.wings.insert("1.0", ", ".join(s.get("wing_names", DEFAULT_WING_NAMES)))
        self.wings.edit_modified(False)
        self.wings.bind("<<Modified>>", self.on_calls_or_wings)
        ttk.Label(row, style="Hint.TLabel", wraplength=330, justify="left",
                  text="Comma separated. Say “Squad <name>” before a Wingmen order: the droid picks "
                       "that wing in the game's comm menu (needs the game link). “Wingmen, …” "
                       "sends the order to all ships."
                  ).pack(side="left", padx=12, anchor="n")


        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", pady=(8, 0), before=self.winfo_children()[0])   # always visible
        self.state_label = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.state_label.pack(side="left")
        ttk.Button(bottom, text="Save", style="Accent.TButton", command=self.save).pack(side="right")
        self._loading = False
        self.schedule_vocab()
        self.show_example()

    # -------------------------------------------------------- personality
    def personality_settings(self):
        key = next((k for k, l in self.pers_keys if l == self.pers_var.get()), hud.DEFAULT_PERSONALITY)
        return {"personality": key, "call_player": " ".join(self.you_var.get().split()),
                "beep_captions": bool(self.captions_var.get())}

    def show_example(self):
        """Three sample HUD lines in the chosen personality."""
        w = hud.Writer(self.personality_settings(), self.personalities)
        name = self.name_var.get().strip() or "R2"
        state = {"hull": 72, "shields": 45, "hostiles": 3}
        lines = [hud.answer_line(w, "status", "positive", state, ""),
                 hud.event_line(w, "kill", "", "victory"),
                 hud.event_line(w, "hull_critical", "18", "panic")]
        self.example.configure(text="\n".join(f"{name}: {l}" for l in lines if l))

    # -------------------------------------------------------------- state
    def get_variants(self):
        lines = [normalize(l) for l in self.variants.get("1.0", "end").splitlines()]
        out = []
        for l in lines:
            if l and l not in out:
                out.append(l)
        return out

    def set_variants(self, items):
        self._loading = True
        self.variants.delete("1.0", "end")
        self.variants.insert("1.0", "\n".join(items))
        self.variants.edit_modified(False)
        self._loading = False

    def mark_dirty(self):
        self.dirty = True
        self.state_label.configure(text="● unsaved changes")

    def on_name(self):
        if self._loading:
            return
        if self.auto:
            self.set_variants(name_variants(self.name_var.get()))
        self.mark_dirty()
        self.schedule_vocab()

    def on_variants(self, _event):
        if not self.variants.edit_modified():
            return
        self.variants.edit_modified(False)
        if self._loading:
            return
        self.auto = False
        self.mark_dirty()
        self.schedule_vocab()

    def on_calls_or_wings(self, event):
        w = event.widget
        if not w.edit_modified():
            return
        w.edit_modified(False)
        if self._loading:
            return
        self.mark_dirty()
        self.schedule_vocab()

    def get_wing_names(self):
        names = [normalize(n) for n in re.split(r"[,\n]", self.wings.get("1.0", "end"))]
        return list(dict.fromkeys(n for n in names if n))

    def all_words(self):
        forms = self.get_variants() + [f for fs in parse_callsigns(self.calls.get("1.0", "end")).values()
                                       for f in fs] + self.get_wing_names()
        return {w for f in forms for w in f.split()}

    def rebuild(self):
        self.auto = True
        self.set_variants(name_variants(self.name_var.get()))
        self.mark_dirty()
        self.schedule_vocab()

    # --------------------------------------------------------- vocabulary
    def schedule_vocab(self):
        if self._vocab_after:
            self.after_cancel(self._vocab_after)
        self._vocab_after = self.after(700, self.check_vocab)

    def show_vocab(self):
        words = sorted(self.all_words())
        unknown = [w for w in words if self._vocab.get(w) is False]
        if not words:
            self.vocab_info.configure(text="Enter a name.", style="Hint.TLabel")
        elif unknown:
            self.vocab_info.configure(
                text=f"⚠ The speech model doesn't know: {', '.join(unknown)}. Lines with these words "
                     "can't be recognized; try spelling it the way it sounds (e.g. “art two”).",
                style="Warn.TLabel")
        elif any(w not in self._vocab for w in words):
            self.vocab_info.configure(text="Checking words against the speech model…", style="Hint.TLabel")
        else:
            self.vocab_info.configure(text="✓ All words are known to the speech model.", style="Ok.TLabel")

    def check_vocab(self):
        self._vocab_after = None
        words = sorted(self.all_words() - set(self._vocab))
        self.show_vocab()
        if not words or self._vocab_running or not os.path.isdir(self.model_path):
            return
        self._vocab_running = True
        results = queue.Queue()

        def work():                         # background thread: never touch tkinter here
            try:
                missing = set(missing_words(self.model_path, words))
                results.put({w: w not in missing for w in words})
            except Exception:
                results.put({})

        def poll():
            try:
                res = results.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            self._vocab.update(res)
            self._vocab_running = False
            self.show_vocab()
            self.check_vocab()

        threading.Thread(target=work, daemon=True).start()
        self.after(100, poll)

    # --------------------------------------------------------------- save
    def save(self):
        name = self.name_var.get().strip()
        variants = self.get_variants()
        if not name or not variants:
            messagebox.showerror("Droid name", "Enter a name and at least one way it is recognized.",
                                 parent=self)
            return False
        save_droid_settings(self.path, name, variants, **self.personality_settings())
        callsigns = parse_callsigns(self.calls.get("1.0", "end"))
        wing_names = self.get_wing_names()
        update_settings(self.path, {"callsigns": callsigns, "wing_names": wing_names})
        self.dirty = False
        self.state_label.configure(text="")
        self.set_status(f"Droid name saved: “{name}”. A running Droid Commander uses it right away.")
        self.on_saved(name, variants, callsigns, wing_names)
        return True
