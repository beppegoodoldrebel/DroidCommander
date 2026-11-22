"""Notice when the mod's controls change (e.g. after a Fate of the Galaxy update) and offer fixes.

At every start the editor compares the controls the mod names in its Controlconfigdefaults.tbl
with the ones it saw last time (settings.json "controls_seen"):
  - a new control (e.g. CUSTOM_CONTROL_4 switched on as "Toggle Ion Cannon")
        -> offer a voice command for it, with phrases made from its name;
  - a control a command uses that now means something else (FotG 2 turned TOGGLE_GLIDING into
    "Toggle Active Pause"), also found the first time by comparing the command's words with
    the control's name -> offer to rename the command to match, or switch it off;
  - a control a command uses that the mod switched off -> offer to switch the command off.
"""

import json
import os
import tkinter as tk
from tkinter import ttk

from . import theme
from .game_controls import NOT_FOR_VOICE, phrase_from_label, phrases_from_label
from .phrases import normalize
from .settings_io import update_settings

SEEN_KEY = "controls_seen"
FILLER = {"toggle", "target", "the", "my", "a", "of", "to", "on", "set", "cycle", "show", "mode",
          "and", "for", "in", "with", "end", "mission"}


def _words(text):
    return {w for w in normalize(text).split() if w not in FILLER}


def _uses(editor):
    """control -> [command index] for the enabled commands."""
    used = {}
    for i, c in enumerate(editor.commands):
        if not c.get("enabled", True):
            continue
        for a in c.get("actions", []):
            if "bind" in a:
                used.setdefault(a["bind"], []).append(i)
    return used


def _mismatch(cmd, label):
    """True if nothing in the command's name or phrases talks about what the control now does."""
    said = _words(cmd.get("name", "")) | {w for p in cmd.get("phrases", []) for w in _words(p)}
    return not (said & _words(phrase_from_label(label)))


def find_changes(editor, seen):
    """(new, changed, off): new [(control, label)], changed [(control, old label, label, [cmd idx])],
    off [(control, label, [cmd idx])]."""
    cat = editor.catalog
    now = cat.snapshot()
    used = _uses(editor)
    old = (seen or {}).get("labels")
    new = []
    if old is not None:                         # first time: nothing is "new", the mod was just found
        new = [(n, l) for n, l in now.items() if n not in old and n not in used and n not in NOT_FOR_VOICE]
    changed = []
    for n, idxs in used.items():
        label = now.get(n)
        if not label:
            continue
        was = (old or {}).get(n)
        if was is not None and was != label:
            # the mod renamed it: a real change of meaning if the two names share no word
            # ("Toggle S-foils" -> "Toggle Wing Lock"), not a cosmetic one ("… S-Foils")
            bad = idxs if not (_words(was) & _words(label)) else []
        elif was is None:
            # never seen: compare with what the commands say (FotG 2's glide -> "Toggle Active Pause")
            bad = [i for i in idxs if _mismatch(editor.commands[i], label)]
        else:
            bad = []
        if bad:
            changed.append((n, was, label, bad))
    off = [(n, cat.label(n), idxs) for n, idxs in used.items() if cat.disabled(n)]
    return new, changed, off


def check_controls(editor):
    """Run at start and when the mod folder changes; shows the dialog if something needs a decision."""
    cat = editor.catalog
    if not cat.mod:
        return
    try:
        with open(editor.settings_path, encoding="utf-8-sig") as f:
            seen = json.load(f).get(SEEN_KEY)
    except (OSError, ValueError):
        seen = None
    mod_name = os.path.basename(os.path.dirname(cat.mod_dir) if cat.mod_dir else "") or "the mod"
    new, changed, off = find_changes(editor, seen)
    current = {"mod": mod_name, "labels": cat.snapshot()}
    if not (new or changed or off):
        if seen != current:
            update_settings(editor.settings_path, {SEEN_KEY: current})
        return
    ControlsChangedDialog(editor, mod_name, new, changed, off, current)


class ControlsChangedDialog(tk.Toplevel):
    def __init__(self, editor, mod_name, new, changed, off, current):
        super().__init__(editor.root)
        self.ed = editor
        self.current = current
        self.configure(bg=theme.C["bg"])
        self.title("Game controls changed")
        self.transient(editor.root)
        C = theme.C
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"The controls of {mod_name} are not what your commands expect.",
                  style="Big.TLabel").pack(anchor="w")
        ttk.Label(frm, style="Hint.TLabel", wraplength=720, justify="left",
                  text="This happens after a mod update. Choose what to do; you can change everything "
                       "later in the Commands tab.").pack(anchor="w", pady=(2, 8))
        self.new_vars, self.changed_vars, self.off_vars = [], [], []
        if new:
            box = ttk.LabelFrame(frm, text="New controls — add a voice command for them?", padding=8)
            box.pack(fill="x", pady=(0, 8))
            for n, label in new:
                v = tk.BooleanVar(value=True)
                says = " / ".join(f"“{p}”" for p in phrases_from_label(label))
                ttk.Checkbutton(box, variable=v, text=f"{label}   — say {says}").pack(anchor="w")
                self.new_vars.append((v, n, label))
        if changed:
            box = ttk.LabelFrame(frm, text="Controls that now do something else", padding=8)
            box.pack(fill="x", pady=(0, 8))
            for n, was, label, idxs in changed:
                for i in idxs:
                    cmd = editor.commands[i]
                    row = ttk.Frame(box)
                    row.pack(fill="x", pady=2)
                    what = f"“{cmd['name']}” presses {n}, which the mod now calls “{label}”"
                    if was:
                        what += f" (was “{was}”)"
                    ttk.Label(row, text=what, wraplength=700, justify="left").pack(anchor="w")
                    v = tk.StringVar(value="rename")
                    opts = ttk.Frame(row)
                    opts.pack(anchor="w", padx=(18, 0))
                    for val, text in (("rename", f"Rename to “{label}” (say “{phrase_from_label(label)}”)"),
                                      ("disable", "Switch the command off"), ("keep", "Keep it as it is")):
                        ttk.Radiobutton(opts, text=text, value=val, variable=v).pack(side="left", padx=(0, 12))
                    self.changed_vars.append((v, i, label))
        if off:
            box = ttk.LabelFrame(frm, text="Controls the mod switched off", padding=8)
            box.pack(fill="x", pady=(0, 8))
            for n, label, idxs in off:
                for i in idxs:
                    v = tk.BooleanVar(value=True)
                    ttk.Checkbutton(box, variable=v, text=f"Switch off “{editor.commands[i]['name']}” "
                                                          f"({label} does nothing in this mod)").pack(anchor="w")
                    self.off_vars.append((v, i))
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Apply", style="Accent.TButton", command=self.apply).pack(side="right")
        ttk.Button(btns, text="Ignore", command=self.ignore).pack(side="right", padx=6)
        ttk.Button(btns, text="Ask me later", command=self.destroy).pack(side="right")
        theme.polish(self)
        self.update_idletasks()
        r = editor.root
        self.geometry(f"+{r.winfo_rootx() + 80}+{r.winfo_rooty() + 80}")
        self.grab_set()

    def remember(self):
        update_settings(self.ed.settings_path, {SEEN_KEY: self.current})

    def ignore(self):
        self.remember()
        self.destroy()

    def apply(self):
        ed = self.ed
        done = []
        for v, i, label in self.changed_vars:
            cmd = ed.commands[i]
            if v.get() == "rename":
                cmd["name"] = label
                cmd["phrases"] = phrases_from_label(label)
                done.append(f"renamed “{label}”")
            elif v.get() == "disable":
                cmd["enabled"] = False
                done.append(f"switched off “{cmd['name']}”")
        for v, i in self.off_vars:
            if v.get():
                ed.commands[i]["enabled"] = False
                done.append(f"switched off “{ed.commands[i]['name']}”")
        picked = [(n, label) for v, n, label in self.new_vars if v.get()]
        if picked:
            ed.add_control_commands(picked)
            done.append(f"added {len(picked)} command(s)")
        else:
            ed.refresh_list()
            ed.load_current()
            ed.changed()
            ed.run_vocab()
        self.remember()
        self.destroy()
        if done:
            ed.tabbar.select(1)
            ed.set_status("Game controls: " + ", ".join(done) + ". Press Save to keep the changes.")
