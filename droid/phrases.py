"""Phrase normalisation, matching and Vosk grammar building."""

import json
import os
import re
from difflib import SequenceMatcher

DIGITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def normalize(text):
    """'R2, open S-foils!' -> 'r two open s foils'."""
    t = text.lower()
    t = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", t)
    t = re.sub(r"\d", lambda m: " " + DIGITS[int(m.group())] + " ", t)
    t = re.sub(r"[^a-z\[\]' ]+", " ", t)
    return " ".join(t.split())


DROID = "Droid"     # the default addressee: commands start with the droid's own name


def command_call(cmd, callsigns):
    """Who a command is addressed to: DROID or the name of a callsign (e.g. 'Wingmen')."""
    call = cmd.get("call") or DROID
    return call if call in callsigns else DROID


class PhraseBook:
    """Maps recognised text to commands.

    Every command is addressed to someone: the droid (its name is the wake word) or
    another callsign such as "Wingmen". The text must start with one of that
    addressee's spoken forms; the rest is then matched only against that addressee's
    phrases.

    Vosk's grammar mode builds a small language model from the phrases rather than
    forcing an exact phrase, so results can contain stray words ("full power will to
    engines"). Matching is therefore exact first, then fuzzy on the word sequence.
    """

    def __init__(self, commands, wake_words, fuzzy=0.75, wake_skip=1, callsigns=None, wing_names=None):
        from .squad import WINGMEN, WING_PREFIX
        self.fuzzy = fuzzy
        self.wake_skip = wake_skip
        self.wake_words = sorted({normalize(w) for w in wake_words if w.strip()},
                                 key=len, reverse=True)
        self.callsigns = {name: sorted({normalize(f) for f in forms if f.strip()}, key=len, reverse=True)
                          for name, forms in (callsigns or {}).items() if name != DROID}
        self.forms = {DROID: self.wake_words, **self.callsigns}
        # "Squad Alpha, cover me" (or "Alpha wing, ...") uses the wingmen's phrases, sent to that
        # wing only. A bare name ("Alpha, ...") is not accepted: short names trigger by mistake.
        self.wing_group = WINGMEN if WINGMEN in self.callsigns else next(iter(self.callsigns), None)
        self.wing_forms = {}
        if self.wing_group:
            for n in dict.fromkeys(normalize(w) for w in (wing_names or []) if normalize(w)):
                self.wing_forms[WING_PREFIX + n] = [f"squad {n}", f"{n} wing"]
        # every spoken prefix, longest first, with the addressee it belongs to
        self.prefixes = sorted(((f, g) for g, fs in {**self.forms, **self.wing_forms}.items() for f in fs),
                               key=lambda x: len(x[0]), reverse=True)
        self.groups = {g: {} for g in self.forms}       # addressee -> {phrase: command}
        self.by_phrase = {}                              # all phrases (any addressee)
        self.duplicates = []
        for cmd in commands:
            if not cmd.get("enabled", True):
                continue
            group = self.groups[command_call(cmd, self.callsigns)]
            for p in cmd.get("phrases", []):
                n = normalize(p)
                if not n:
                    continue
                if n in group and group[n] is not cmd:
                    self.duplicates.append((n, group[n]["name"], cmd["name"]))
                group[n] = cmd
                self.by_phrase.setdefault(n, cmd)

    def split_prefix(self, text):
        """Return (addressee or None, remainder). Tolerates `wake_skip` stray leading words."""
        tokens = text.split()
        for skip in range(self.wake_skip + 1):
            for form, group in self.prefixes:
                ft = form.split()
                if tokens[skip:skip + len(ft)] == ft:
                    return group, " ".join(tokens[skip + len(ft):])
                # typed as one word ("wingmen" for "wing men")
                if len(ft) > 1 and skip < len(tokens) and tokens[skip] == "".join(ft):
                    return group, " ".join(tokens[skip + 1:])
        return None, text

    def split_wake(self, text):
        """Return (addressed to the droid or a callsign, remainder)."""
        group, rest = self.split_prefix(text)
        return group is not None, rest

    def phrase_group(self, group):
        """The addressee whose phrases apply: a wing uses the wingmen's phrases."""
        return self.wing_group if group in self.wing_forms else group

    def best_match(self, rest, group=None):
        """Return (command or None, score), looking only at `group`'s phrases if given."""
        group = self.phrase_group(group)
        phrases = self.groups.get(group, {}) if group else self.by_phrase
        if rest in phrases:
            return phrases[rest], 1.0
        rt = rest.split()
        if not rt or not phrases:
            return None, 0.0
        scored = []
        for phrase, cmd in phrases.items():
            scored.append((SequenceMatcher(None, rt, phrase.split()).ratio(), cmd))
        scored.sort(key=lambda x: x[0], reverse=True)
        best, cmd = scored[0]
        if best < self.fuzzy:
            return None, best
        for score, other in scored[1:]:     # ambiguous between two different commands?
            if other is not cmd:
                if best - score < 0.08:
                    return None, best
                break
        return cmd, best

    def match(self, text):
        """Return (command or None, had_wake_word, remainder, score)."""
        text = normalize(text.replace("[unk]", " "))  # [unk] never matches a phrase
        group, rest = self.split_prefix(text)
        cmd, score = self.best_match(rest, group)
        return cmd, group is not None, rest, score

    def match_full(self, text):
        """Like match(), plus the addressee that was recognised (or None)."""
        text = normalize(text.replace("[unk]", " "))
        group, rest = self.split_prefix(text)
        cmd, score = self.best_match(rest, group)
        return cmd, group, rest, score

    def grammar(self, with_wake, without_wake):
        g = set()
        for group, phrases in self.groups.items():
            for p in phrases:
                if without_wake:
                    g.add(p)
                if with_wake:
                    for w in self.forms[group]:
                        g.add(f"{w} {p}")
                    if group == self.wing_group:
                        for forms in self.wing_forms.values():
                            for w in forms:
                                g.add(f"{w} {p}")
        if with_wake:
            for form, _ in self.prefixes:
                g.add(f"{form} [unk]")
        g.add("[unk]")
        return sorted(g)

    def all_words(self):
        words = set()
        for p in list(self.by_phrase) + [f for f, g in self.prefixes if g not in self.wing_forms]:
            words.update(p.split())
        return words


def missing_words(model_path, words):
    """Words the Vosk model doesn't know (they would be silently dropped from the grammar).

    Uses the model's own word list if present, otherwise asks Vosk in a subprocess
    (the engine's `vocabprobe` command) and parses its 'Ignoring word missing in
    vocabulary' warnings.
    """
    words = sorted(w for w in words if w != "[unk]")
    for rel in ("graph/words.txt", "words.txt"):
        path = os.path.join(model_path, rel)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                vocab = {line.split()[0] for line in f if line.strip()}
            return [w for w in words if w not in vocab]
    import subprocess
    from .paths import engine_command
    p = subprocess.run(engine_command("vocabprobe", os.path.abspath(model_path)), input=json.dumps(words),
                       capture_output=True, text=True, timeout=120,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return re.findall(r"missing in vocabulary: '([^']+)'", p.stderr)


def to_json(grammar):
    return json.dumps(grammar)
