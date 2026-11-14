"""Game link: a small Lua script inside FreeSpace Open writes game events (kills, hits...)
to droid_link.log; this module installs that script and reads the events back.

Script:  game_link/zz_droidcommander-sct.lua  ->  <mod>/data/tables/lua/
Events:  <FSO user folder>/<mod folder>/data/missions/droid_link.log
         one line per event:  seq|mission time|event|detail
"""

import glob
import json
import os
import random
import shutil
import threading
import time

from .paths import resource
SCRIPT_NAME = "zz_droidcommander-sct.lua"
SCRIPT_SRC = resource("game_link", SCRIPT_NAME)
EVENT_FILE = "droid_link.log"

# event -> (label, default reaction)
EVENTS = {
    "kill":           ("You destroy an enemy fighter",            dict(response="victory", chance=1.0, cooldown=2)),
    "kill_capital":   ("You destroy a capital ship / big target",  dict(response="victory", chance=1.0, cooldown=0)),
    "teamkill":       ("You destroy a friendly ship",             dict(response="sad", chance=1.0, cooldown=0)),
    "ally_down":      ("A friendly ship is destroyed",            dict(response="sad", chance=0.7, cooldown=6)),
    "hit_shield":     ("Your shields are hit",                    dict(response="scared", chance=0.2, cooldown=8)),
    "hit_hull":       ("Your hull is hit",                        dict(response="scared", chance=0.6, cooldown=5)),
    "hull_low":       ("Hull below 50%",                          dict(response="alarm", chance=1.0, cooldown=0)),
    "hull_critical":  ("Hull below 25%",                          dict(response="panic", chance=1.0, cooldown=0)),
    "collision":      ("You collide with something",              dict(response="scared", chance=0.6, cooldown=5)),
    "subsystem_lost": ("One of your subsystems is destroyed",     dict(response="alarm", chance=1.0, cooldown=3)),
    "player_death":   ("You are destroyed",                       dict(response="sad", chance=1.0, cooldown=0)),
    "mission_start":  ("Mission starts",                          dict(response="greeting", chance=1.0, cooldown=0)),
    "mission_end":    ("Mission ends",                            dict(response="chatter", chance=1.0, cooldown=0)),
}
SMALL_TYPES = {"fighter", "bomber", "fighter/bomber", "support", "stealth", "escape pod", "ship"}
MIN_GAP = 1.2           # seconds between any two reactions
COMMAND_PRIORITY = 1.5  # no reaction this soon after the droid answered a voice command


def event_config(settings):
    """Per-event reaction settings (defaults filled in)."""
    user = (settings.get("events") or {})
    cfg = {}
    for key, (_, default) in EVENTS.items():
        c = dict(default, enabled=True)
        c.update(user.get(key) or {})
        cfg[key] = c
    return cfg


# ------------------------------------------------------------------ locations
def kn_portable_root(players_dir):
    """…/kn_portable/HardLightProductions/FreeSpaceOpen/data/players -> …/kn_portable"""
    return os.path.normpath(os.path.join(players_dir, "..", "..", "..", ".."))


def user_root(players_dir):
    """FreeSpace Open's user folder: …/HardLightProductions/FreeSpaceOpen"""
    return os.path.normpath(os.path.join(players_dir, "..", ".."))


def library_dir(players_dir):
    root = kn_portable_root(players_dir)
    try:
        with open(os.path.join(root, "KnossosNET", "settings.json"), encoding="utf-8") as f:
            base = json.load(f).get("base_path")
        if base and os.path.isdir(base):
            return base
    except (OSError, ValueError):
        pass
    return os.path.join(root, "Library")


def _version(path):
    v = os.path.basename(os.path.normpath(path)).split("-")[-1]
    return [int(x) if x.isdigit() else 0 for x in v.split(".")]


def package_dir(version_dir):
    """Where the script goes inside one mod version.

    FotG 1 (…/FotG_R-1.1.3) has its 'data' folder right there; FotG 2 (…/FotG_2-2.0.2) is split
    into packages (FG_Core, FG_Maps1…), each with its own 'data': the core package is used.
    """
    if os.path.isdir(os.path.join(version_dir, "data")):
        return version_dir
    subs = sorted(d for d in glob.glob(os.path.join(version_dir, "*")) if os.path.isdir(os.path.join(d, "data")))
    if not subs:
        return None
    core = [d for d in subs if "core" in os.path.basename(d).lower()]
    return (core or subs)[0]


def find_mod_dirs(players_dir, mod_prefix="FotG"):
    """Script folders of the installed Fate of the Galaxy versions, newest first.

    …/Library/FotG_R/FotG_R-1.1.3, …/Library/FotG_2/FotG_2-2.0.2/FG_Core
    """
    versions = glob.glob(os.path.join(library_dir(players_dir), f"{mod_prefix}*", f"{mod_prefix}*-*"))
    dirs = [(v, package_dir(v)) for v in versions if os.path.isdir(v)]
    return [p for v, p in sorted(((v, p) for v, p in dirs if p), key=lambda x: _version(x[0]), reverse=True)]


def script_status(mod_dir):
    """'installed', 'outdated' or 'missing'."""
    dest = os.path.join(mod_dir, "data", "tables", "lua", SCRIPT_NAME)
    if not os.path.exists(dest):
        return "missing"
    with open(dest, "rb") as a, open(SCRIPT_SRC, "rb") as b:
        return "installed" if a.read() == b.read() else "outdated"


def install(mod_dir):
    dest_dir = os.path.join(mod_dir, "data", "tables", "lua")
    os.makedirs(dest_dir, exist_ok=True)
    shutil.copy2(SCRIPT_SRC, os.path.join(dest_dir, SCRIPT_NAME))


def uninstall(mod_dir):
    dest = os.path.join(mod_dir, "data", "tables", "lua", SCRIPT_NAME)
    if os.path.exists(dest):
        os.remove(dest)


MANUAL_MOD_DIR = None    # set from settings.json "game_link" → "mod_dir" (chosen in the Events tab)


def valid_mod_dir(path):
    """The mod folder for a chosen path (the mod folder itself, or its data folder), or None."""
    if not path:
        return None
    path = os.path.normpath(path)
    if os.path.basename(path).lower() == "data" and os.path.isdir(path):
        path = os.path.dirname(path)
    if not os.path.isdir(path):
        return None
    found = package_dir(path)           # a mod version (with 'data', or split into packages)
    if found:
        return found
    # the folder that holds the mod's versions (…/FotG_2): take the newest version inside
    subs = [(d, package_dir(d)) for d in glob.glob(os.path.join(path, "*")) if os.path.isdir(d)]
    subs = sorted(((d, p) for d, p in subs if p), key=lambda x: _version(x[0]), reverse=True)
    return subs[0][1] if subs else None


def mod_dir(players_dir, manual=None):
    """The mod folder to install into: the one chosen by hand, else the newest one found."""
    if manual:
        return valid_mod_dir(manual)
    dirs = find_mod_dirs(players_dir) if players_dir else []
    return dirs[0] if dirs else None


def user_roots(players_dir):
    """FreeSpace Open user folders where the game writes droid_link.log."""
    roots = []
    if players_dir:
        roots.append(user_root(players_dir))
    if MANUAL_MOD_DIR:                      # Knossos portable: <root>/HardLightProductions/FreeSpaceOpen
        p = os.path.normpath(MANUAL_MOD_DIR)
        for _ in range(5):
            p = os.path.dirname(p)
            roots.append(os.path.join(p, "HardLightProductions", "FreeSpaceOpen"))
    if os.environ.get("APPDATA"):           # a normal (non-portable) install
        roots.append(os.path.join(os.environ["APPDATA"], "HardLightProductions", "FreeSpaceOpen"))
    return [r for r in dict.fromkeys(roots) if os.path.isdir(r)]


def find_event_file(players_dir):
    """The most recently written droid_link.log in FreeSpace Open's user folder, or None."""
    found = []
    for root in user_roots(players_dir):
        found += glob.glob(os.path.join(root, "data", "missions", EVENT_FILE))
        found += glob.glob(os.path.join(root, "*", "data", "missions", EVENT_FILE))
        found += glob.glob(os.path.join(root, "*", "*", "data", "missions", EVENT_FILE))   # FotG 2 packages
    return max(found, key=os.path.getmtime) if found else None


STATE_FILE = "droid_state.txt"
STATE_MAX_AGE = 3.0      # seconds: an older snapshot means you're not flying right now


def read_state(players_dir):
    """Latest snapshot of your ship as a dict of numbers/strings, {} if dead, None if not flying."""
    events = find_event_file(players_dir)
    if not events:
        return None
    path = os.path.join(os.path.dirname(events), STATE_FILE)
    try:
        if time.time() - os.path.getmtime(path) > STATE_MAX_AGE:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            pairs = [l.strip().split("=", 1) for l in f if "=" in l]
    except OSError:
        return None
    state = {}
    for k, v in pairs:
        try:
            state[k] = float(v) if k not in ("target", "wings") else v
        except ValueError:
            state[k] = v
    if state.get("alive", 1) == 0:
        return {}
    return state


# question -> (label, example phrases)
QUESTIONS = {
    "status":  ("Are you OK? (hull, shields, recent hits)",
                ["are you ok", "are you okay", "how are you", "status report", "are you all right"]),
    "damage":  ("Are we hit? (damage)",
                ["are we hit", "are we damaged", "damage report", "how bad is it"]),
    "shields": ("How are the shields?",
                ["how are the shields", "shield status", "are the shields up"]),
    "kill":    ("Did we get him? (a kill in the last seconds)",
                ["did we get him", "did i get him", "is he dead", "got him"]),
    "clear":   ("Are we clear? (enemies left)",
                ["are we clear", "is it clear", "any more enemies", "anyone left"]),
    "target":  ("Is the target damaged?",
                ["is the target damaged", "target status", "how is the target"]),
    "energy":  ("Do we have weapon energy?",
                ["do we have energy", "weapons status", "are the weapons charged"]),
}


def answer(question, state, last_hit=0.0, last_kill=0.0, now=None):
    """(response, explanation) for a question, judged on the ship's state.

    Responses: positive / negative, or a stronger one (panic, alarm, victory, sad), or
    unknown when the game link has nothing to say (not flying, no target...).
    """
    now = now or time.time()
    if state is None:
        return "unknown", "no game data (not flying, or game link not installed)"
    if state == {}:
        return "sad", "your ship is destroyed"
    hull, shields = state.get("hull", -1), state.get("shields", -1)
    hit_recently = now - last_hit < 8
    if question == "status":
        if 0 <= hull < 25:
            return "panic", f"hull {hull:.0f}%"
        ok = hull >= 60 and (shields < 0 or shields >= 30) and not hit_recently
        return ("positive" if ok else "negative"), f"hull {hull:.0f}%, shields {shields:.0f}%" + \
            (", just hit" if hit_recently else "")
    if question == "damage":
        damaged = 0 <= hull < 90 or hit_recently
        return ("negative" if damaged else "positive"), f"hull {hull:.0f}%" + (", just hit" if hit_recently else "")
    if question == "shields":
        if shields < 0:
            return "unknown", "no shields"
        if shields < 20:
            return "alarm", f"shields {shields:.0f}%"
        return ("positive" if shields >= 50 else "negative"), f"shields {shields:.0f}%"
    if question == "kill":
        got = now - last_kill < 12
        return ("victory" if got else "negative"), "a kill just now" if got else "no recent kill"
    if question == "clear":
        n = state.get("hostiles")
        if n is None:
            return "unknown", "enemy count unknown"
        return ("positive" if n == 0 else "negative"), f"{n:.0f} hostile ships left"
    if question == "target":
        t = state.get("target")
        if not t:
            return "unknown", "no target"
        pct, _, name = str(t).partition("|")
        try:
            pct = float(pct)
        except ValueError:
            return "unknown", "target unknown"
        return ("positive" if pct <= 50 else "negative"), f"{name} at {pct:.0f}%"
    if question == "energy":
        e = state.get("energy", -1)
        if e < 0:
            return "unknown", "energy unknown"
        return ("positive" if e >= 50 else "negative"), f"weapon energy {e:.0f}%"
    return "unknown", "unknown question"


def parse_line(line):
    parts = line.rstrip("\r\n").split("|", 3)
    if len(parts) < 3:
        return None
    event = parts[2]
    detail = parts[3] if len(parts) > 3 else ""
    if event == "kill":                      # split fighters from capital ships
        kind = detail.split("|", 1)[0].lower()
        if kind not in SMALL_TYPES:
            event = "kill_capital"
    return event, detail


# --------------------------------------------------------------------- reader
class GameLink:
    """Tails droid_link.log in a background thread and calls on_event(event, detail)."""

    def __init__(self, players_dir, on_event, on_status=None, poll=0.1):
        self.players_dir = players_dir
        self.on_event = on_event
        self.on_status = on_status or (lambda state, path: None)
        self.poll = poll
        self.path = None
        self.offset = 0
        self._mtime = None
        self._stop = threading.Event()
        self._started = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _locate(self):
        path = find_event_file(self.players_dir)
        if path != self.path:
            self.path = path
            # start at the end of an old file; read a file written after we started from the top
            fresh = path and os.path.getmtime(path) >= self._started
            self.offset = 0 if fresh else (os.path.getsize(path) if path else 0)
            self._mtime = os.path.getmtime(path) if path else None
            self.on_status("connected" if fresh else "waiting", path)

    def _run(self):
        self.on_status("waiting", None)
        last_scan = 0
        buf = ""
        while not self._stop.is_set():
            now = time.time()
            if now - last_scan > 3 or self.path is None:
                last_scan = now
                try:
                    self._locate()
                except OSError:
                    pass
            if self.path:
                try:
                    st = os.stat(self.path)
                    size = st.st_size
                    rewritten = size < self.offset or (st.st_mtime != self._mtime and size <= self.offset
                                                       and self._mtime is not None)
                    if rewritten:                    # rewritten at mission start
                        self.offset, buf = 0, ""
                    self._mtime = st.st_mtime
                    if size > self.offset:
                        with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(self.offset)
                            buf += f.read()
                            self.offset = f.tell()
                        *lines, buf = buf.split("\n")
                        for line in lines:
                            ev = parse_line(line)
                            if ev and ev[0] == "session":
                                self.on_status("connected", self.path)
                            elif ev:
                                self.on_event(*ev)
                except OSError:
                    pass
            self._stop.wait(self.poll)


class Reactions:
    """Decides whether the droid reacts to an event (enabled, chance, cooldowns)."""

    def __init__(self, config):
        self.config = config
        self.last = {}
        self.last_any = 0.0
        self.last_command = 0.0

    def command_answered(self):
        self.last_command = time.time()

    def pick(self, event):
        """Return the response to play, or None."""
        c = self.config.get(event)
        if not c or not c.get("enabled", True):
            return None
        now = time.time()
        if now - self.last.get(event, 0) < c.get("cooldown", 0):
            return None
        if now - self.last_any < MIN_GAP or now - self.last_command < COMMAND_PRIORITY:
            return None
        if random.random() > c.get("chance", 1.0):
            return None
        self.last[event] = self.last_any = now
        return c.get("response")
