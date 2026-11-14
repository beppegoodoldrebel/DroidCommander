"""Diagnose playback while the microphone is open (run from the project folder).

Plays the same chirp in several configurations; note which ones you hear.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import sounddevice as sd
from droid.synth import make

data, sr = make("ready", seed=1)
data16 = np.interp(np.arange(0, len(data), sr / 16000), np.arange(len(data)), data).astype(np.float32)


def wasapi_output():
    apis = sd.query_hostapis()
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] > 0 and "MH752" in d["name"] and "WASAPI" in apis[d["hostapi"]]["name"]:
            return i
    return None


tests = [
    ("A  mic CLOSED, 44.1 kHz, default output", None, data, sr, False),
    ("B  mic OPEN,   44.1 kHz, default output", None, data, sr, True),
    ("C  mic OPEN,   16 kHz,   default output", None, data16, 16000, True),
    ("D  mic OPEN,   48 kHz,   WASAPI output", wasapi_output(), None, 48000, True),
]

for label, dev, d, rate, mic in tests:
    if d is None:
        d = np.interp(np.arange(0, len(data), sr / rate), np.arange(len(data)), data).astype(np.float32)
    print(f"{label} ...", flush=True)
    stream = None
    try:
        if mic:
            stream = sd.RawInputStream(samplerate=16000, blocksize=1600, dtype="int16", channels=1)
            stream.start()
            time.sleep(0.5)
        sd.play(d * 0.8, rate, device=dev)
        sd.wait()
    except Exception as e:
        print(f"   ERROR: {e}")
    finally:
        if stream:
            stream.stop()
            stream.close()
    time.sleep(1.2)
print("Done.")
