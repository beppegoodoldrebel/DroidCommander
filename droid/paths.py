"""Where things live.

Running from source: everything stays in the project folder (as during development).
Installed (.exe built with PyInstaller):
  - program files (speech model, game-link script, default config) are read-only, next to the exe;
  - the user's data (settings, commands, voices, sound files) lives in %APPDATA%\\DroidCommander.
"""

import os
import shutil
import sys

FROZEN = getattr(sys, "frozen", False)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if FROZEN:
    RESOURCE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    EXE_DIR = os.path.dirname(sys.executable)
    DATA_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "DroidCommander")
else:
    RESOURCE_DIR = PROJECT_DIR
    EXE_DIR = None
    DATA_DIR = PROJECT_DIR

ENGINE_EXE = "DroidCommanderEngine.exe"


def resource(*parts):
    """A read-only file shipped with the program."""
    return os.path.join(RESOURCE_DIR, *parts)


def resolve_model(path):
    """Absolute path of the speech model: the user's data folder first, then the program's."""
    if os.path.isabs(path):
        return path
    for base in (DATA_DIR, RESOURCE_DIR):
        candidate = os.path.join(base, path)
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(RESOURCE_DIR, path)


def ensure_user_data():
    """First run: copy the default settings into the user's data folder.

    Installed: %APPDATA%\\DroidCommander\\config. From source (e.g. a fresh clone, where the
    personal config/ folder isn't in the repository): the project's config/ folder.
    """
    os.makedirs(os.path.join(DATA_DIR, "config"), exist_ok=True)
    os.makedirs(os.path.join(DATA_DIR, "sounds", "voices"), exist_ok=True)
    defaults = resource("defaults", "config")
    for name in ("settings.json", "commands.json", "voices.json"):
        dest = os.path.join(DATA_DIR, "config", name)
        if not os.path.exists(dest) and os.path.exists(os.path.join(defaults, name)):
            shutil.copy2(os.path.join(defaults, name), dest)


def engine_command(*args):
    """Command line that runs Droid Commander's engine (listener, vocabulary probe...)."""
    if FROZEN:
        return [os.path.join(EXE_DIR, ENGINE_EXE), *args]
    exe = sys.executable
    d, base = os.path.split(exe)
    if base.lower() == "pythonw.exe" and os.path.exists(os.path.join(d, "python.exe")):
        exe = os.path.join(d, "python.exe")        # pythonw has no usable stdout
    return [exe, "-u", "-m", "droid", *args]
