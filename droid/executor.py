"""Runs a voice command in the game, through the game link.

A command is a list of actions:
  {"bind": "MAX_THROTTLE"}                 a game control (FreeSpace Open's name), optional "repeat"
  {"wait": 200}                            a pause in milliseconds
  {"ask": "clear"}                         a question to the droid (answered by app.py, no control)
The game link script presses the controls inside the game, so no key binding, keyboard layout or
window focus is involved.
"""

from .controls import CONTROLS


class CommandError(Exception):
    pass


ACTION_KEYS = {"bind", "repeat", "wait", "ask"}


def check_command(command):
    """Raise CommandError if a command can't run (unknown control, old keyboard action...)."""
    actions = command.get("actions", [])
    if not actions:
        raise CommandError("the command has no actions")
    for a in actions:
        if "key" in a or "mouse" in a:
            raise CommandError("keyboard keys and mouse buttons aren't used any more: "
                               "replace this action with a game control")
        if "bind" in a and a["bind"] not in CONTROLS:
            raise CommandError(f"'{a['bind']}' is not a FreeSpace Open control")
        if not set(a) <= ACTION_KEYS or not ({"bind", "wait", "ask"} & set(a)):
            raise CommandError(f"invalid action: {a}")


def lua_body(command):
    """The command as the game link script reads it: 'MAX_THROTTLE:1,WAIT:200,INCREASE_ENGINE:6'."""
    parts = []
    for a in command.get("actions", []):
        if "bind" in a:
            parts.append(f"{a['bind']}:{max(1, int(a.get('repeat', 1)))}")
        elif "wait" in a:
            parts.append(f"WAIT:{max(0, int(a['wait']))}")
    return ",".join(parts)


class Executor:
    def __init__(self, lua=None):
        self.lua = lua               # luacmd.LuaControls, or None when the game link is switched off
        self.last_note = ""          # what the game link pressed, or why it couldn't

    def execute(self, command):
        check_command(command)
        if not lua_body(command):
            return                   # a question: nothing to press
        if self.lua is None:
            raise CommandError("the game link is switched off (Events tab)")
        ok, note = self.lua.send(command)
        self.last_note = note
        if not ok:
            raise CommandError(note)
