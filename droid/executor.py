"""Turns a command definition into simulated input for the game."""

import time

from . import keysender
from .keymap import parse_key, MOUSE_BUTTONS
from .winutil import game_has_focus


class CommandError(Exception):
    pass


class Executor:
    def __init__(self, bindings, game_settings):
        self.bindings = bindings
        self.require_focus = game_settings.get("require_focus", True)
        self.process_names = game_settings.get("process_names", ["fs2_open"])
        self.hold_ms = game_settings.get("key_hold_ms", 60)
        self.gap_ms = game_settings.get("key_gap_ms", 50)
        self.lua = None              # luacmd.LuaControls: press controls through the game link
        self.last_route = None       # how the last command was sent: "game link" or "keys"
        self.last_note = ""          # why the game link wasn't used, or what it pressed

    def plan(self, command):
        """Validate a command and return a list of steps. Raises CommandError."""
        self.bindings.maybe_reload()
        steps = []
        for a in command.get("actions", []):
            repeat = int(a.get("repeat", 1))
            hold = int(a.get("hold_ms", self.hold_ms))
            if "wait" in a:
                steps.append(("wait", int(a["wait"]), 0))
                continue
            if "ask" in a:                      # a question to the droid: no keys to press
                continue
            if "bind" in a:
                r = self.bindings.resolve(a["bind"])
                if r is None:
                    raise CommandError(
                        f"'{a['bind']}' has no keyboard/mouse input in the preset "
                        f"({self.bindings.describe(a['bind'])})")
                step = ("key", r.value, hold) if r.kind == "key" else ("mouse", r.value, hold)
            elif "key" in a:
                try:
                    step = ("key", parse_key(a["key"]), hold)
                except ValueError as e:
                    raise CommandError(str(e))
            elif "mouse" in a:
                if a["mouse"] not in MOUSE_BUTTONS:
                    raise CommandError(f"unknown mouse button '{a['mouse']}'")
                step = ("mouse", a["mouse"], hold)
            else:
                raise CommandError(f"invalid action: {a}")
            for i in range(repeat):
                if i:
                    steps.append(("wait", self.gap_ms, 0))
                steps.append(step)
        if not steps and not any("ask" in a for a in command.get("actions", [])):
            raise CommandError("the command has no actions")
        return steps

    def check_focus(self):
        if not self.require_focus:
            return
        ok, name = game_has_focus(self.process_names)
        if not ok:
            raise CommandError(f"the game is not in the foreground (active window: '{name or '?'}')")

    def execute(self, command):
        self.last_note = ""
        if self.lua is not None:
            from .luacmd import can_run
            if can_run(command):
                ok, note = self.lua.send(command)
                self.last_note = note
                if ok:
                    self.last_route = "game link"
                    return []
        self.last_route = "keys"
        steps = self.plan(command)
        self.check_focus()
        for kind, value, hold in steps:
            if kind == "wait":
                time.sleep(value / 1000.0)
            elif kind == "key":
                keysender.press_combo(value, hold)
            elif kind == "mouse":
                keysender.click_mouse(value, hold)
        return steps
