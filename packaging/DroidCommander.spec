# PyInstaller build: two executables sharing one folder.
#   DroidCommander.exe        the app window (no console)
#   DroidCommanderEngine.exe  the listener started by LAUNCH! (console app, run hidden) + CLI tools
# Build with packaging\build.ps1
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(SPECPATH, "droid.ico")
MODEL = "vosk-model-small-en-us-0.15"

vosk_datas, vosk_binaries, vosk_hidden = collect_all("vosk")
datas = vosk_datas + [
    (os.path.join(ROOT, "models", MODEL), os.path.join("models", MODEL)),
    (os.path.join(ROOT, "game_link"), "game_link"),
    (os.path.join(ROOT, "defaults"), "defaults"),
    (os.path.join(SPECPATH, "licenses"), "licenses"),
]
common = dict(
    pathex=[ROOT],
    binaries=vosk_binaries,
    datas=datas,
    hiddenimports=vosk_hidden,
    excludes=["lupa", "PyInstaller", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)

gui = Analysis([os.path.join(SPECPATH, "run_gui.py")], **common)
engine = Analysis([os.path.join(SPECPATH, "run_engine.py")], **common)

gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="DroidCommander",
              console=False, icon=ICON, upx=False)
engine_exe = EXE(PYZ(engine.pure), engine.scripts, [], exclude_binaries=True, name="DroidCommanderEngine",
                 console=True, icon=ICON, upx=False)

COLLECT(gui_exe, gui.binaries, gui.datas,
        engine_exe, engine.binaries, engine.datas,
        name="DroidCommander", upx=False)
