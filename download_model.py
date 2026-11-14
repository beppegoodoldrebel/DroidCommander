"""Download the small English Vosk speech model (~40 MB) into the models/ folder."""

import os
import sys
import urllib.request
import zipfile

NAME = "vosk-model-small-en-us-0.15"
URL = f"https://alphacephei.com/vosk/models/{NAME}.zip"
ROOT = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(ROOT, "models")


def main():
    target = os.path.join(MODELS, NAME)
    if os.path.isdir(target):
        print(f"Model already present: {target}")
        return
    os.makedirs(MODELS, exist_ok=True)
    zpath = os.path.join(MODELS, NAME + ".zip")

    last = [-1]

    def progress(blocks, bsize, total):
        if total > 0:
            pct = min(100, blocks * bsize * 100 // total)
            if pct // 10 != last[0]:
                last[0] = pct // 10
                sys.stdout.write(f"  {pct}%")
                sys.stdout.flush()

    print(f"Downloading {URL}")
    urllib.request.urlretrieve(URL, zpath, progress)
    print("\nExtracting...")
    with zipfile.ZipFile(zpath) as z:
        for m in z.namelist():  # refuse paths escaping the models folder
            dest = os.path.realpath(os.path.join(MODELS, m))
            if not dest.startswith(os.path.realpath(MODELS) + os.sep):
                raise RuntimeError(f"invalid path in zip archive: {m}")
        z.extractall(MODELS)
    os.remove(zpath)
    print(f"Done: {target}")


if __name__ == "__main__":
    main()
