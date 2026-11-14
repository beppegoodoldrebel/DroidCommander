"""Find which audio output you can actually hear (run from the project folder).

Step 1 plays a chirp through Windows itself (winsound, default device).
Step 2 plays a 2-second tone on every output device, one at a time.
"""
import os
import sys
import tempfile
import time
import winsound

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import sounddevice as sd
import soundfile as sf
from droid.synth import make

data, sr = make("ready", seed=1)
wav = os.path.join(tempfile.gettempdir(), "droid_test_chirp.wav")
sf.write(wav, np.tile(data, 3), sr)

print("STEP 1: chirp played by WINDOWS (winsound) on the default device...", flush=True)
winsound.PlaySound(wav, winsound.SND_FILENAME)
time.sleep(1.5)

print("\nSTEP 2: 2-second tone on each output device (python / sounddevice)\n", flush=True)
t = np.arange(int(44100 * 2.0)) / 44100
tone = (0.5 * np.sin(2 * np.pi * 660 * t)).astype(np.float32)
apis = sd.query_hostapis()
for i, d in enumerate(sd.query_devices()):
    if d["max_output_channels"] <= 0 or apis[d["hostapi"]]["name"] != "MME":
        continue
    print(f"  >>> NOW PLAYING ON [{i}] {d['name']}", flush=True)
    try:
        sd.play(tone, 44100, device=i)
        sd.wait()
    except Exception as e:
        print(f"      ERROR: {e}")
    time.sleep(1.5)
print("\nDone.")
