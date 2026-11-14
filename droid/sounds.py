"""Droid voice: plays the active voice's response, either one of its sound files or synthesized.

Two playback backends:
  - "winsound" (default): Windows' own PlaySound on the default output device.
    Plays WAV files only, so every sound is rendered to a temporary 16-bit WAV
    (volume applied) before playing. Works on systems where PortAudio is silent.
  - "sounddevice": PortAudio, lets you pick a specific output device.
"""

import os
import random
import tempfile

AUDIO_EXT = (".wav", ".ogg", ".flac", ".mp3")


def list_devices(kind):
    """[(index, full name)] of the audio devices of a kind ("input" or "output"), one per device.

    Windows lists every device once per driver API (MME, DirectSound, WASAPI, WDM-KS). We use
    the MME entry, which accepts any sample rate (Windows resamples), and show the full name
    from DirectSound (MME cuts names at 31 characters).
    """
    import sounddevice as sd
    devices, apis = sd.query_devices(), sd.query_hostapis()
    ch = "max_input_channels" if kind == "input" else "max_output_channels"
    mme = next((i for i, a in enumerate(apis) if a["name"] == "MME"), 0)
    full = [d["name"] for d in devices
            if d[ch] > 0 and "DirectSound" in apis[d["hostapi"]]["name"]]
    out = []
    for i, d in enumerate(devices):
        if d[ch] > 0 and d["hostapi"] == mme and "Sound Mapper" not in d["name"]:
            out.append((i, next((f for f in full if f.startswith(d["name"])), d["name"])))
    return out


def default_device_name(kind):
    import sounddevice as sd
    try:
        idx = sd.default.device[0 if kind == "input" else 1]
        short = sd.query_devices(idx)["name"]
    except Exception:
        return ""
    return next((n for _, n in list_devices(kind) if n.startswith(short)), short)


def find_device(spec, kind):
    """sounddevice index for a saved device (full name, name fragment or index); None = default."""
    if spec is None or spec == "":
        return None
    if isinstance(spec, int):
        return spec
    devices = list_devices(kind)
    for i, name in devices:                      # exact name first
        if name == spec:
            return i
    for i, name in devices:                      # then a fragment, either way round
        if spec.lower() in name.lower() or name.lower() in spec.lower():
            return i
    print(f"  [audio] {kind} device '{spec}' not found, using the Windows default")
    return None


def find_output_device(spec):
    return find_device(spec, "output")


def output_devices():
    """(index, name) of every output device, one per device."""
    return list_devices("output")


class SoundBank:
    def __init__(self, folder, volume=0.8, device=None, backend="winsound",
                 voices_path="config/voices.json"):
        from .voices import VoiceStore
        self.folder = folder
        self.default_volume = float(volume)   # settings.json; voices.json "volume" overrides it
        self.backend = backend
        self.voices = VoiceStore(voices_path)
        self.device = find_output_device(device) if backend == "sounddevice" else None
        self._cache = {}          # path -> (data, sr)
        self._wav_cache = {}      # path -> rendered temp wav (winsound)
        self._tmpdir = os.path.join(tempfile.gettempdir(), "droid_commander")
        self._slot = 0

    def _load(self, path):
        if path not in self._cache:
            import soundfile as sf
            data, sr = sf.read(path, dtype="float32", always_2d=False)
            self._cache[path] = (data, sr)
        return self._cache[path]

    @property
    def volume(self):
        """Current master volume, re-read from voices.json so changes apply live."""
        return self.voices.volume(self.default_volume)

    def _render(self, data, sr, name, volume):
        """Write data (volume applied) as 16-bit PCM WAV in the temp folder."""
        import numpy as np
        import soundfile as sf
        os.makedirs(self._tmpdir, exist_ok=True)
        path = os.path.join(self._tmpdir, name)
        sf.write(path, np.clip(data * volume, -1, 1), sr, subtype="PCM_16")
        return path

    def _resolve(self, what, voice=None):
        """Return (data, sr, source_path or None) for a response type or a file path.

        The voice (given, or the active one from voices.json) decides: a "files" voice plays
        one of its sound files for that response at random; a synthesized voice (or a files
        voice with no file for that response) synthesizes it.
        """
        if voice is None and os.path.isfile(what):          # explicit file path
            return (*self._load(what), what)
        v = voice if voice is not None else self.voices.active()
        if v.get("mode") == "files":
            files = [f for f in (v.get("files") or {}).get(what, []) if os.path.isfile(f)]
            if files:
                path = random.choice(files)
                return (*self._load(path), path)
        from .synth import make
        return (*make(what, voice=v), None)

    def play(self, what="ack", device=None, voice=None):
        """'what' is a mood name (ack/error/unknown/ready/chatter) or a file path.

        Passing 'voice' plays with that voice instead of the active one (used by the voice editor).
        """
        if not what:
            return
        try:
            data, sr, source = self._resolve(what, voice)
            vol = self.volume
            if self.backend == "sounddevice":
                import sounddevice as sd
                sd.play(data * vol, sr, device=self.device if device is None else device)
                return
            import winsound
            if source is not None:            # user file: render once per volume, reuse
                key = (source, round(vol, 2))
                if key not in self._wav_cache:
                    self._wav_cache[key] = self._render(
                        data, sr, f"file_{len(self._wav_cache)}.wav", vol)
                wav = self._wav_cache[key]
            else:                             # synth: new sound each time, rotate files
                self._slot = (self._slot + 1) % 8
                wav = self._render(data, sr, f"synth_{self._slot}.wav", vol)
            winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception as e:  # sound must never break command execution
            print(f"  [audio] cannot play '{what}': {e}")
