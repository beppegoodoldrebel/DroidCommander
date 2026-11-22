"""Talks to the game link script to press game controls inside FreeSpace Open.

The Lua script (game_link/zz_droidcommander-sct.lua) reads droid_cmd.txt a few times per
second, presses the named controls ("MAX_THROTTLE") with FSO's Lua button controls exactly as
if you pressed their key, and answers in droid_ack.txt. No keyboard layout, key binding or
window focus is involved, and controls bound only to a joystick work too.
"""

import os
import threading
import time

from . import gamelink

KEEP_LINES = 8           # the command file holds the last few commands (the script runs the new ones)

CMD_FILE = "droid_cmd.txt"
ACK_FILE = "droid_ack.txt"
ACK_TIMEOUT = 0.6        # seconds: the script reads commands about 12 times per second
ORDER_TIMEOUT = 1.5      # wingman orders wait for the comm menu to open and change page
NOT_FLYING = "no mission running (or the game link isn't installed: Events tab)"


class LuaControls:
    def __init__(self, players_dir_fn):
        self.players_dir_fn = players_dir_fn       # FSO's data/players folder (may be found later)
        self._last_seq = 0
        self._lines = []                           # [(seq, line)] still in the command file
        self._lock = threading.Lock()              # commands and droid messages come from 2 threads
        self.answered = False

    def _mission_dir(self):
        """Folder the script reads from, if a mission is running right now."""
        players_dir = self.players_dir_fn()
        if gamelink.read_state(players_dir) is None:          # not flying (or no game link)
            return None
        events = gamelink.find_event_file(players_dir)
        return os.path.dirname(events) if events else None

    def _write(self, path, text):
        """Replace the file in one go. Windows refuses while the game is reading it
        ("Access is denied"): the game reads it in a moment, so try again for a while."""
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        for attempt in range(25):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 24:
                    raise
                time.sleep(0.01)

    def send(self, command):
        """(True, what was pressed) if the game pressed the command's controls, else (False, reason)."""
        from .executor import lua_body
        return self._roundtrip(lua_body(command), ACK_TIMEOUT + self._waits(command))

    @staticmethod
    def _waits(command):
        return sum(int(a.get("wait", 0)) for a in command.get("actions", [])) / 1000.0

    def send_order(self, shortcut, wing=None):
        """A wingman order: the shortcut, then "All Fighters" or the wing picked by name in the comm menu."""
        target = f"wing:{wing}" if wing else "all"
        return self._roundtrip(f"order:{shortcut}:{target}", ORDER_TIMEOUT)

    def check(self, names):
        """Ask the game which control names it knows, without pressing anything.

        Returns (known set, unknown set), or raises RuntimeError with the reason.
        """
        names = sorted(set(names))
        ok, note = self._roundtrip("check:" + ",".join(names), ACK_TIMEOUT)
        if not ok:
            raise RuntimeError(note)
        parts = dict(p.split("=", 1) for p in note.split(";") if "=" in p)
        split = lambda s: {n for n in s.split(",") if n}
        return split(parts.get("known", "")), split(parts.get("unknown", ""))

    def say(self, sender, text):
        """Show "<sender>: <text>" among the game's HUD messages. Doesn't wait; False if not flying."""
        text = " ".join(str(text).split())[:200]
        sender = " ".join(str(sender).replace("|", "/").split())[:24] or "R2"
        folder = self._mission_dir()
        if folder is None or not text:
            return False
        try:
            self._post(folder, f"say:{sender}|{text}")
        except OSError:
            return False
        return True

    def _post(self, folder, body):
        """Add a command to the command file (keeping the last few). Returns its seq."""
        with self._lock:
            seq = max(int(time.time() * 1000), self._last_seq + 1)
            self._last_seq = seq
            self._lines = (self._lines + [(seq, f"{seq}|{body}")])[-KEEP_LINES:]
            self._write(os.path.join(folder, CMD_FILE), "\n".join(l for _, l in self._lines) + "\n")
            return seq

    def _forget(self, folder, seq):
        """Take a command out of the file (it came too late: it must not run any more)."""
        with self._lock:
            self._lines = [(s, l) for s, l in self._lines if s != seq]
            try:
                self._write(os.path.join(folder, CMD_FILE), "".join(l + "\n" for _, l in self._lines))
            except OSError:
                pass

    def _roundtrip(self, body, timeout):
        """Write a command, wait for the game's answer. self.answered: the game did answer."""
        self.answered = False
        folder = self._mission_dir()
        if folder is None:
            return False, NOT_FLYING
        if gamelink.outdated_in_game(self.players_dir_fn()):
            return False, "the game runs an older game link: restart FreeSpace Open"
        try:
            seq = self._post(folder, body)
        except OSError as e:
            return False, f"can't write {CMD_FILE}: {e}"
        ack_path = os.path.join(folder, ACK_FILE)
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(0.02)
            try:
                with open(ack_path, encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue
            for line in lines:
                parts = line.strip().split("|", 2)
                if len(parts) == 3 and parts[0] == str(seq):
                    self.answered = True
                    return parts[1] == "ok", parts[2]
        self._forget(folder, seq)
        return False, "the game didn't answer (paused, or not in a mission?)"
