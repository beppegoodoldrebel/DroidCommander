"""Press game controls through the game link instead of the keyboard.

The Lua script inside FreeSpace Open (game_link/zz_droidcommander-sct.lua) reads
droid_cmd.txt a few times per second and presses the named controls ("MAX_THROTTLE") with
FSO's Lua button controls, exactly as if you pressed their key; it confirms in droid_ack.txt.

Why: no keyboard layout problems, controls bound only to a joystick work too, and the game
window doesn't need to be in front. When the game link isn't there, the game isn't running a
mission or nothing answers in time, the executor falls back to pressing keys.
"""

import os
import time

from . import gamelink

CMD_FILE = "droid_cmd.txt"
ACK_FILE = "droid_ack.txt"
ACK_TIMEOUT = 0.6        # seconds: the script reads commands about 12 times per second
ORDER_TIMEOUT = 1.5      # wingman orders wait for the comm menu to open and change page


def can_run(command):
    """Only commands made of game actions ("bind", optionally repeated) go through the game link.

    Fixed keys, mouse buttons, pauses and held keys keep using the keyboard. Wingman orders
    have their own path (send_order).
    """
    actions = command.get("actions", [])
    return bool(actions) and all(set(a) <= {"bind", "repeat"} for a in actions)


class LuaControls:
    def __init__(self, players_dir_fn):
        self.players_dir_fn = players_dir_fn       # bindings.players_dir may change (follow pilot)
        self._last_seq = 0

    def _mission_dir(self):
        """Folder the script reads from, if a mission is running right now."""
        players_dir = self.players_dir_fn()
        if gamelink.read_state(players_dir) is None:          # not flying (or no game link)
            return None
        events = gamelink.find_event_file(players_dir)
        return os.path.dirname(events) if events else None

    def _write(self, path, text):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)

    def send(self, command):
        """(True, detail) if the game pressed the controls, else (False, reason)."""
        body = ",".join(f"{a['bind']}:{max(1, int(a.get('repeat', 1)))}" for a in command["actions"])
        return self._roundtrip(body, ACK_TIMEOUT)

    def send_order(self, shortcut, wing=None):
        """A wingman order: the shortcut, then "All Fighters" or the wing picked by name in the comm menu."""
        target = f"wing:{wing}" if wing else "all"
        return self._roundtrip(f"order:{shortcut}:{target}", ORDER_TIMEOUT)

    def _roundtrip(self, body, timeout):
        """Write a command, wait for the game's answer. self.answered: the game did answer."""
        self.answered = False
        folder = self._mission_dir()
        if folder is None:
            return False, "no mission running with the game link"
        seq = max(int(time.time() * 1000), self._last_seq + 1)
        self._last_seq = seq
        cmd_path, ack_path = os.path.join(folder, CMD_FILE), os.path.join(folder, ACK_FILE)
        try:
            self._write(cmd_path, f"{seq}|{body}\n")
        except OSError as e:
            return False, f"can't write {CMD_FILE}: {e}"
        end = time.time() + timeout
        while time.time() < end:
            time.sleep(0.02)
            try:
                with open(ack_path, encoding="utf-8", errors="replace") as f:
                    parts = f.readline().strip().split("|", 2)
            except OSError:
                continue
            if len(parts) == 3 and parts[0] == str(seq):
                self.answered = True
                return parts[1] == "ok", parts[2]
        try:                                       # too late: make sure it isn't run after the keys
            self._write(cmd_path, "")
        except OSError:
            pass
        return False, "the game didn't answer"
