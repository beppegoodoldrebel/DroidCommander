"""What the droid writes among the game's HUD messages, in its personality.

Like the translation of an astromech's beeps: "R2: [excited whistle] Got him! Great shot, Boss!".
Only answers to your questions, problems (why an order couldn't be done) and the game events
the droid reacts to; only on your screen, through the game link.

The lines live in config/personalities.json (editable; the built-in file fills what's missing):
one block per personality, one list of lines per situation, picked at random. Settings:
  game_link.hud_messages   true/false (Events tab)
  droid.personality        "rebel", "cheerful", "grumpy", "nervous", "by_the_book" (Droid tab)
  droid.call_player        how the droid calls you ("Boss"), used by the lines with {you}
  droid.beep_captions      true: "[excited whistle]" before the line
"""

import json
import os
import random
import string

from .paths import resource

USER_FILE = os.path.join("config", "personalities.json")
DEFAULT_PERSONALITY = "rebel"
YOU_CHANCE = 0.45          # how often a line that names you is picked, when there is one


def enabled(game_link_settings):
    """HUD messages on? (older settings stored a level name: anything but 'off' counts as on)."""
    v = (game_link_settings or {}).get("hud_messages", True)
    return v not in (False, "off", "false", 0, None)


def load_personalities(path=USER_FILE):
    """{"captions": {...}, "personalities": {...}}: the user's file over the built-in one."""
    def read(p):
        try:
            with open(p, encoding="utf-8-sig") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}
    base = read(resource("defaults", "config", "personalities.json"))
    user = read(path) if path and os.path.abspath(path) != os.path.abspath(
        resource("defaults", "config", "personalities.json")) else {}
    out = {"captions": dict(base.get("captions") or {}), "personalities": {}}
    out["captions"].update(user.get("captions") or {})
    for key, p in (base.get("personalities") or {}).items():
        out["personalities"][key] = {"label": p.get("label", key), "lines": dict(p.get("lines") or {}),
                                     "captions": dict(p.get("captions") or {})}
    for key, p in (user.get("personalities") or {}).items():
        mine = out["personalities"].setdefault(key, {"label": key, "lines": {}, "captions": {}})
        mine["label"] = p.get("label", mine["label"])
        mine["lines"].update(p.get("lines") or {})
        mine["captions"].update(p.get("captions") or {})
    return out


def personality_labels(data=None):
    """[(key, label)] in file order."""
    data = data or load_personalities()
    return [(k, p.get("label", k)) for k, p in data["personalities"].items()]


class _Values(dict):
    def __missing__(self, key):
        return ""


def plural(n, word):
    n = int(n)
    return f"{n} {word}" + ("" if n == 1 else "s")


class Writer:
    """Turns a situation into a line in the droid's personality."""

    def __init__(self, droid_settings, data=None):
        d = droid_settings or {}
        self.data = data or load_personalities()
        key = d.get("personality") or DEFAULT_PERSONALITY
        self.personality = self.data["personalities"].get(key) or \
            self.data["personalities"].get(DEFAULT_PERSONALITY) or {"lines": {}, "captions": {}}
        self.you = " ".join(str(d.get("call_player") or "").split())
        self.captions = d.get("beep_captions", True)

    def _pick(self, key, fallback):
        lines = self.personality["lines"].get(key) or self.personality["lines"].get(fallback) or []
        if not self.you:
            lines = [l for l in lines if "{you}" not in l]
        if not lines:
            return None
        with_you = [l for l in lines if "{you}" in l]
        if with_you and random.random() < YOU_CHANCE:
            return random.choice(with_you)
        rest = [l for l in lines if "{you}" not in l] or lines
        return random.choice(rest)

    def caption(self, mood):
        if not self.captions or not mood:
            return ""
        pool = self.personality.get("captions", {}).get(mood) or self.data["captions"].get(mood) or []
        return random.choice(pool) if pool else ""

    def line(self, key, mood=None, fallback="answer.generic", **values):
        """The text for situation `key` ("answer.status.positive", "event.kill", "problem"), or None."""
        template = self._pick(key, fallback)
        if template is None:
            return None
        vals = _Values(values)
        vals["you"] = self.you
        try:
            text = string.Formatter().vformat(template, (), vals)
        except (ValueError, IndexError):
            text = template
        text = " ".join(text.split())
        text = text[:1].upper() + text[1:]
        cap = self.caption(mood)
        return f"{cap} {text}" if cap else text


def answer_values(question, state, why):
    """Numbers and names for the answer lines, from the ship snapshot."""
    s = state or {}
    vals = {"why": why}
    for k in ("hull", "shields", "energy"):
        if isinstance(s.get(k), (int, float)) and s[k] >= 0:
            vals[k] = f"{s[k]:.0f}"
    if isinstance(s.get("hostiles"), (int, float)):
        vals["hostiles"] = plural(s["hostiles"], "hostile")
    t = str(s.get("target") or "")
    if "|" in t:
        pct, _, name = t.partition("|")
        vals["target"] = name or "The target"
        try:
            vals["pct"] = f"{float(pct):.0f}"
        except ValueError:
            pass
    return vals


def answer_line(writer, question, response, state, why):
    return writer.line(f"answer.{question}.{response}", mood=response, fallback="answer.generic",
                       **answer_values(question, state, why))


def event_line(writer, event, detail, mood):
    """Line for a game event the droid reacts to, or None for events it doesn't comment."""
    if event not in ("kill", "kill_capital", "teamkill", "ally_down", "hull_low", "hull_critical",
                     "subsystem_lost"):
        return None
    vals = {}
    if event in ("hull_low", "hull_critical"):
        vals["hull"] = detail or ("50" if event == "hull_low" else "25")
    if event == "subsystem_lost":
        vals["subsystem"] = (detail or "a subsystem").lower()
    return writer.line(f"event.{event}", mood=mood, fallback=None, **vals)


def problem_line(writer, reason):
    return writer.line("problem", mood="error", fallback=None, reason=str(reason).rstrip("."))
