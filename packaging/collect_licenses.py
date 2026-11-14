"""Gather the licenses of everything shipped in the installer into packaging/licenses/."""
import importlib.metadata as md
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "licenses")
# runtime packages bundled by PyInstaller (build tools like pyinstaller, lupa, pip are not shipped)
SHIPPED = ["numpy", "sounddevice", "soundfile", "cffi", "pycparser", "requests", "urllib3", "idna",
           "certifi", "charset-normalizer", "tqdm", "srt", "websockets", "colorama", "typing_extensions"]

NOTICE = """Droid Commander — third-party components
=========================================

Droid Commander includes the following software. Each one keeps its own license; the license
texts are in this folder.

Component                       License                      Source
------------------------------  ---------------------------  ------------------------------------------
Python 3.12 runtime             PSF License                  https://www.python.org
Vosk speech recognition         Apache License 2.0           https://alphacephei.com/vosk
vosk-model-small-en-us-0.15     Apache License 2.0           https://alphacephei.com/vosk/models
PortAudio (via sounddevice)     MIT                          http://www.portaudio.com
libsndfile (via soundfile)      LGPL 2.1                     https://libsndfile.github.io/libsndfile
Tcl/Tk (tkinter)                Tcl/Tk license (BSD-style)   https://www.tcl.tk
{packages}
Fate of the Galaxy and FreeSpace Open are separate projects by their own authors and are not
included. Droid Commander is an unofficial fan tool, not affiliated with Lucasfilm.
"""


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    rows = []
    for name in SHIPPED:
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            continue
        lic = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "see license file"
        rows.append(f"{name + ' ' + dist.version:<31} {lic.splitlines()[0][:27]:<28} PyPI: {name}")
        dest = os.path.join(OUT, name)
        for f in dist.files or []:
            if any(k in str(f).upper() for k in ("LICEN", "COPYING", "NOTICE")) and not str(f).endswith((".py", ".pyc")):
                src = f.locate()
                if os.path.isfile(src):
                    os.makedirs(dest, exist_ok=True)
                    shutil.copy2(src, os.path.join(dest, os.path.basename(str(f))))
    base = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
    for cand in (os.path.join(sys.base_prefix, "LICENSE.txt"), os.path.join(base, "LICENSE.txt")):
        if os.path.exists(cand):
            shutil.copy2(cand, os.path.join(OUT, "Python-LICENSE.txt"))
            break
    # Vosk and its model are Apache 2.0 (the package ships no license file): use the standard text
    apache = md.distribution("requests").locate_file("requests-%s.dist-info/licenses/LICENSE"
                                                      % md.distribution("requests").version)
    if os.path.exists(apache):
        shutil.copy2(apache, os.path.join(OUT, "Apache-2.0 (Vosk and speech model).txt"))
    readme = os.path.join(ROOT, "models", "vosk-model-small-en-us-0.15", "README")
    if os.path.exists(readme):
        shutil.copy2(readme, os.path.join(OUT, "vosk-model-small-en-us-0.15 README.txt"))
    sp = os.path.dirname(md.distribution("sounddevice").locate_file("sounddevice.py"))
    for sub, fname, target in (("_sounddevice_data", "README.md", "PortAudio binaries README.md"),
                               ("_soundfile_data", "COPYING", "libsndfile COPYING (LGPL-2.1).txt")):
        for dirpath, _, files in os.walk(os.path.join(sp, sub)):
            if fname in files:
                shutil.copy2(os.path.join(dirpath, fname), os.path.join(OUT, target))
                break
    with open(os.path.join(OUT, "THIRD_PARTY_NOTICES.txt"), "w", encoding="utf-8") as f:
        f.write(NOTICE.format(packages="\n".join(rows)))
    print("licenses collected in", OUT, ":", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
