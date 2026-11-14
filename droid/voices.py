"""Droid voices: built-in presets (synth.PRESETS) plus user voices in config/voices.json.

A voice is either synthesized (slider parameters) or made of sound files: for each response
type (ack, error, unknown, ready, chatter) a list of files, one picked at random each time.
Sound files of a voice are copied into sounds/voices/<voice>/<response>/ so a voice is
self-contained.

voices.json:
    {
        "active": "R2-D2 style",
        "volume": 0.7,
        "custom": {
            "My grumpy R5": {"pitch": 700, ...},
            "Real R2": {"pitch": 1100, ..., "mode": "files",
                        "files": {"ack": ["sounds/voices/Real R2/ack/beep1.wav"], ...}}
        }
    }
"""

import json
import os
import re
import shutil

from .synth import DEFAULT_VOICE, MOODS, PARAM_KEYS, PRESETS, complete

SYNTH, FILES = "synth", "files"
VOICES_DIR = os.path.join("sounds", "voices")
AUDIO_TYPES = (".wav", ".ogg", ".flac", ".mp3")


def _with_extras(params, src):
    """Slider parameters plus the voice's source mode and sound files."""
    v = dict(params)
    v["mode"] = FILES if src.get("mode") == FILES else SYNTH
    v["files"] = {m: list(src.get("files", {}).get(m, [])) for m in MOODS}
    return v


def load(path):
    data = {"active": DEFAULT_VOICE, "volume": None, "custom": {}}
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
            data["active"] = loaded.get("active", DEFAULT_VOICE)
            vol = loaded.get("volume")
            data["volume"] = None if vol is None else min(1.0, max(0.0, float(vol)))
            data["custom"] = {k: _with_extras(complete(v), v) for k, v in loaded.get("custom", {}).items()}
        except (OSError, ValueError) as e:
            print(f"  [voice] cannot read {path}: {e}")
    return data


def save(path, data):
    def fmt(v):
        parts = [f'"{k}": {round(v[k], 3):g}' for k in PARAM_KEYS if k in v]
        if v.get("mode") == FILES:
            parts.append('"mode": "files"')
        files = {m: fs for m, fs in (v.get("files") or {}).items() if fs}
        if files:
            parts.append('"files": ' + json.dumps(files, ensure_ascii=False))
        return "{" + ", ".join(parts) + "}"

    custom = ",\n".join(f"        {json.dumps(name, ensure_ascii=False)}: {fmt(v)}"
                        for name, v in data["custom"].items())
    volume = "" if data.get("volume") is None else f',\n    "volume": {round(data["volume"], 2):g}'
    text = ('{\n    "active": ' + json.dumps(data["active"], ensure_ascii=False) + volume
            + ',\n    "custom": {\n' + custom + ("\n" if custom else "") + "    }\n}\n")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def names(data):
    return list(PRESETS) + [n for n in data["custom"] if n not in PRESETS]


def params(data, name=None):
    """Full voice: slider parameters + 'mode' + 'files'."""
    name = name or data["active"]
    if name in data["custom"]:
        src = data["custom"][name]
        return _with_extras(complete(src), src)
    return _with_extras(complete(PRESETS.get(name, PRESETS[DEFAULT_VOICE])), {})


def is_builtin(name):
    return name in PRESETS


def voice_folder(name):
    safe = re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "voice"
    return os.path.join(VOICES_DIR, safe)


def adopt_files(name, voice):
    """Copy the voice's sound files into sounds/voices/<name>/<response>/ and point to the copies.

    Files already inside that folder are kept as they are. Returns the updated voice.
    """
    root = voice_folder(name)
    out = dict(voice)
    out["files"] = {}
    for mood in MOODS:
        dest_dir = os.path.join(root, mood)
        kept = []
        for src in (voice.get("files") or {}).get(mood, []):
            if not os.path.isfile(src):
                continue
            if os.path.abspath(src).startswith(os.path.abspath(dest_dir) + os.sep):
                kept.append(os.path.relpath(src).replace("\\", "/"))
                continue
            os.makedirs(dest_dir, exist_ok=True)
            base, ext = os.path.splitext(os.path.basename(src))
            dest, k = os.path.join(dest_dir, base + ext), 2
            while os.path.exists(dest):
                dest, k = os.path.join(dest_dir, f"{base}_{k}{ext}"), k + 1
            shutil.copy2(src, dest)
            kept.append(os.path.relpath(dest).replace("\\", "/"))
        out["files"][mood] = kept
    return out


class VoiceStore:
    """Active voice, reloaded automatically when voices.json changes."""

    def __init__(self, path):
        self.path = path
        self._mtime = None
        self.data = load(path)
        self._stamp()

    def _stamp(self):
        try:
            self._mtime = os.path.getmtime(self.path)
        except OSError:
            self._mtime = None

    def _refresh(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            m = None
        if m != self._mtime:
            self.data = load(self.path)
            self._mtime = m

    def active(self):
        self._refresh()
        return params(self.data)

    def volume(self, default):
        """Master droid volume (0..1) from voices.json, or `default` if not set there."""
        self._refresh()
        v = self.data.get("volume")
        return default if v is None else v
