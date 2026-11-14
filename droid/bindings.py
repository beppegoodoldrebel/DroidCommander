"""Reads FreeSpace Open control presets (data/players/presets/*.json).

The preset can be fixed, or follow a pilot: each pilot file (data/players/<PILOT>.json)
records the preset in use at sections.controls.preset, so when you switch preset in the
game, Droid Commander switches too.
"""

import glob
import json
import os

from .keymap import parse_key, MOUSE_BUTTONS


# ------------------------------------------------------------ discovery helpers
def _read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def guess_players_dir(bindings_file):
    """…/data/players/presets/X.json -> …/data/players"""
    if not bindings_file:
        return ""
    d = os.path.dirname(os.path.abspath(bindings_file))
    return os.path.dirname(d) if os.path.basename(d).lower() == "presets" else d


def detect_players_dir():
    """Find FreeSpace Open's data/players folder on this PC, or ''.

    Looks at the standard user folder (%APPDATA%\\HardLightProductions\\FreeSpaceOpen) and at
    Knossos.NET's library (portable FSO preferences live next to it).
    """
    appdata = os.environ.get("APPDATA", "")
    candidates = [os.path.join(appdata, "HardLightProductions", "FreeSpaceOpen", "data", "players")]
    try:
        base = _read_json(os.path.join(appdata, "KnossosNET", "settings.json")).get("base_path") or ""
        if base:
            candidates.append(os.path.join(os.path.dirname(base), "HardLightProductions",
                                           "FreeSpaceOpen", "data", "players"))
    except (OSError, ValueError, AttributeError):
        pass
    found = [c for c in candidates if os.path.isdir(c) and (list_pilots(c) or list_presets(c))]
    found.sort(key=lambda c: len(list_pilots(c)), reverse=True)
    return found[0] if found else ""


def list_presets(players_dir):
    files = glob.glob(os.path.join(players_dir or "", "presets", "*.json"))
    return sorted(os.path.splitext(os.path.basename(f))[0] for f in files)


def preset_path(players_dir, name):
    return os.path.join(players_dir, "presets", name + ".json")


def pilot_preset(players_dir, pilot):
    """Name of the preset the pilot currently uses, or None."""
    try:
        data = _read_json(os.path.join(players_dir, pilot + ".json"))
        return data["sections"]["controls"]["preset"] or None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_pilots(players_dir):
    """[(pilot, preset name or None)] for every pilot file in the players folder."""
    out = []
    for f in sorted(glob.glob(os.path.join(players_dir or "", "*.json"))):
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            data = _read_json(f)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "sections" in data:
            out.append((name, (data["sections"].get("controls") or {}).get("preset")))
    return out


class Resolved:
    """What we can actually simulate for a bind."""

    def __init__(self, kind, value, source):
        self.kind = kind      # "key" | "mouse"
        self.value = value    # KeyCombo | mouse button name
        self.source = source  # "primary" | "secondary"

    def describe(self):
        return self.value.text if self.kind == "key" else f"MOUSE {self.value}"


class BindingStore:
    """Loads the preset and reloads it automatically when it (or the followed pilot) changes."""

    def __init__(self, path, players_dir=None, pilot=None, follow_pilot=False):
        self.raw = {}       # bind -> {"primary": (cid, input), "secondary": (...)}
        self._mtime = None
        self._pilot_mtime = None
        self.configure(path, players_dir, pilot, follow_pilot)

    @classmethod
    def from_settings(cls, s):
        path = s.get("bindings_file", "")
        return cls(path, s.get("fso_players_dir") or guess_players_dir(path),
                   s.get("pilot"), s.get("follow_pilot", False))

    def configure(self, path, players_dir=None, pilot=None, follow_pilot=False):
        self.fixed_path = path
        self.players_dir = players_dir or guess_players_dir(path)
        self.pilot = pilot
        self.follow_pilot = bool(follow_pilot and pilot)
        self._pilot_mtime = None
        self.path = path
        self._resolve_pilot()
        self.reload()

    @property
    def preset_name(self):
        return os.path.splitext(os.path.basename(self.path))[0] if self.path else "(no preset)"

    def _pilot_file(self):
        return os.path.join(self.players_dir, f"{self.pilot}.json")

    def _resolve_pilot(self):
        """When following a pilot, point self.path at the preset the pilot uses."""
        if not self.follow_pilot:
            self.path = self.fixed_path
            return
        try:
            self._pilot_mtime = os.path.getmtime(self._pilot_file())
        except OSError:
            self._pilot_mtime = None
        name = pilot_preset(self.players_dir, self.pilot)
        if name and os.path.exists(preset_path(self.players_dir, name)):
            self.path = preset_path(self.players_dir, name)
        else:
            self.path = self.fixed_path

    def reload(self):
        if not self.path or not os.path.exists(self.path):   # not configured yet (first run)
            self.raw, self._mtime = {}, None
            return
        data = _read_json(self.path)
        raw = {}
        for a in data.get("actions", []):
            entry = {}
            for slot in ("primary", "secondary"):
                s = a.get(slot) or {}
                entry[slot] = (s.get("cid", "CID_NONE"), s.get("input", "NONE"))
            raw[a["bind"]] = entry
        self.raw = raw
        self._mtime = os.path.getmtime(self.path)

    def maybe_reload(self):
        """Reload if the pilot switched preset or the preset file was edited."""
        try:
            if self.follow_pilot:
                m = os.path.getmtime(self._pilot_file())
                if m != self._pilot_mtime:
                    old = self.path
                    self._resolve_pilot()
                    if self.path != old:
                        self.reload()
                        return True
            if os.path.getmtime(self.path) != self._mtime:
                self.reload()
                return True
        except (OSError, ValueError):
            pass
        return False

    def resolve(self, bind):
        """Return a Resolved for the bind, or None if it has no keyboard/mouse input.

        Keyboard is preferred over mouse; joystick-only binds can't be simulated.
        """
        entry = self.raw.get(bind)
        if entry is None:
            return None
        for wanted in ("CID_KEYBOARD", "CID_MOUSE"):
            for slot in ("primary", "secondary"):
                cid, inp = entry[slot]
                if cid != wanted:
                    continue
                if cid == "CID_KEYBOARD":
                    try:
                        return Resolved("key", parse_key(inp), slot)
                    except ValueError:
                        continue
                if cid == "CID_MOUSE" and inp in MOUSE_BUTTONS:
                    return Resolved("mouse", inp, slot)
        return None

    def describe(self, bind):
        entry = self.raw.get(bind)
        if entry is None:
            return "(bind not found in preset)"
        parts = []
        for slot in ("primary", "secondary"):
            cid, inp = entry[slot]
            if cid != "CID_NONE":
                parts.append(f"{cid.replace('CID_', '')}:{inp}")
        return ", ".join(parts) or "(unbound)"

    def usable_count(self):
        return sum(1 for b in self.raw if not b.endswith("_AXIS") and self.resolve(b))
