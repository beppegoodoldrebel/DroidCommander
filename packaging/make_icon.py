"""Draw the app icon (the same little astromech as the window icon) into packaging/droid.ico.

The .ico holds PNG images at several sizes (supported by Windows Vista and later).
"""
import os
import struct
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from droid import theme  # noqa: E402

SIZES = (256, 64, 48, 32, 16)


def main(out):
    root = tk.Tk()
    root.withdraw()
    theme.apply(root)
    pngs = []
    tmp = tempfile.mkdtemp()
    for size in SIZES:
        img = theme._icon(root, size)
        path = os.path.join(tmp, f"{size}.png")
        img.write(path, format="png")
        with open(path, "rb") as f:
            pngs.append((size, f.read()))
    root.destroy()
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for size, data in pngs:
        s = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", s, s, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(out, "wb") as f:
        f.write(header + entries + blobs)
    print("icon written:", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "droid.ico"))
