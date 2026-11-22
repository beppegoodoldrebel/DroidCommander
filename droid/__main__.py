"""Droid Commander - voice-controlled astromech for FreeSpace Open / Fate of the Galaxy.

  python -m droid app              open the Droid Commander app (configure + launch)
  python -m droid app --active     open it and start listening right away
  python -m droid                  start voice listening in the console
  python -m droid check            validate commands and vocabulary
  python -m droid binds            show which game control each command presses
  python -m droid test "open s foils" [--delay 5]   run a command without voice (needs a mission
                                   running with the game link)
  python -m droid learn            print the name of pressed keys/buttons (for push-to-talk)
  python -m droid sound ack        play a sound (ack/error/unknown/ready/chatter)
  python -m droid mics             list microphones
  python -m droid speakers         play a chirp on every output device, to pick the right one
"""

import argparse
import os
import sys
import time

from . import paths


def main(argv=None):
    # relative paths in settings are relative to the user's data folder
    # (the project folder when running from source, %APPDATA%\DroidCommander when installed)
    paths.ensure_user_data()
    os.chdir(paths.DATA_DIR)
    p = argparse.ArgumentParser(prog="droid", description="Droid Commander")
    p.add_argument("--settings", default="config/settings.json")
    p.add_argument("--commands", default="config/commands.json")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--events", action="store_true", help="print machine-readable event lines (launcher)")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run")
    sub.add_parser("check")
    sub.add_parser("binds")
    t = sub.add_parser("test")
    t.add_argument("phrase")
    t.add_argument("--delay", type=float, default=5.0,
                   help="seconds to wait so you can switch to the game window")
    sub.add_parser("learn")
    s = sub.add_parser("sound")
    s.add_argument("mood", nargs="?", default="ack")
    sub.add_parser("mics")
    sub.add_parser("speakers")
    a = sub.add_parser("app")
    a.add_argument("--active", action="store_true", help="start listening right away")
    a.add_argument("--configure", action="store_true", help="open in configure mode")
    sub.add_parser("edit")                       # old name of "app --configure"
    v = sub.add_parser("vocabprobe")               # internal: which words the speech model knows
    v.add_argument("model")
    args = p.parse_args(argv)

    if args.cmd == "vocabprobe":                # words on stdin; Vosk logs the unknown ones to stderr
        import json
        from vosk import KaldiRecognizer, Model, SetLogLevel
        SetLogLevel(0)
        words = json.loads(sys.stdin.read().lstrip("﻿"))
        KaldiRecognizer(Model(args.model), 16000, json.dumps(words))
        return

    if args.cmd in ("app", "edit"):
        from .editor import run_editor
        mode = "configure" if args.cmd == "edit" else None
        if args.cmd == "app":
            mode = "active" if args.active else "configure" if args.configure else None
        run_editor(args.settings, args.commands, mode)
        return
    if args.cmd == "learn":
        from .triggers import learn
        try:
            learn()
        except KeyboardInterrupt:
            pass
        return
    if args.cmd == "mics":
        import sounddevice as sd
        print(sd.query_devices())
        return

    from .app import DroidApp, load_json
    app = DroidApp(load_json(args.settings), load_json(args.commands), verbose=args.verbose,
                   commands_path=args.commands, settings_path=args.settings,
                   events=args.events)

    if args.cmd == "check":
        n = app.check()
        print("All good." if n == 0 else f"{n} problem(s) found.")
        sys.exit(1 if n else 0)

    if args.cmd == "binds":
        from .controls import Catalog
        from .executor import CommandError, check_command
        from . import gamelink
        cat = Catalog(gamelink.mod_dir(app.players_dir, gamelink.MANUAL_MOD_DIR))
        for cmd in app.commands:
            try:
                check_command(cmd)
            except CommandError as e:
                print(f"  {cmd['name']:<28} !! {e}")
                continue
            parts = [f"{a['bind']} ({cat.label(a['bind'])})" + (f" x{a['repeat']}" if a.get("repeat", 1) > 1 else "")
                     for a in cmd["actions"] if "bind" in a]
            print(f"  {cmd['name']:<28} {' + '.join(parts) or '(question)'}")
        return

    if args.cmd == "test":
        from .executor import CommandError
        cmd, _, rest, _ = app.book.match(args.phrase)
        if cmd is None:
            print(f"No command matches '{rest}'")
            app.sounds.play("unknown"); time.sleep(1)
            sys.exit(1)
        print(f"'{rest}' -> {cmd['name']}. Switch to the game: running in {args.delay:.0f} s...")
        time.sleep(args.delay)
        try:
            from .squad import is_squad_order
            if is_squad_order(cmd):
                app.squad_order(cmd, None)
            else:
                app.executor.execute(cmd)
            print(f"Done: {app.executor.last_note}")
            app.sounds.play(cmd.get("sound", "ack"))
        except CommandError as e:
            print(f"Error: {e}")
            app.sounds.play("error")
        time.sleep(1.5)
        return

    if args.cmd == "speakers":
        from .sounds import output_devices
        import sounddevice as sd
        default = sd.default.device[1]
        app.sounds.backend = "sounddevice"   # device selection needs sounddevice
        print("Playing a chirp on every output device. When you hear it, put the name")
        print('(or part of it) in config/settings.json -> "sound" -> "output_device".\n')
        for idx, name in output_devices():
            mark = "  <- current default" if idx == default else ""
            print(f"  [{idx}] {name}{mark}")
            app.sounds.play("ready", device=idx)
            time.sleep(1.5)
        return

    if args.cmd == "sound":
        app.sounds.play(args.mood)
        time.sleep(1.5)
        return

    app.run()


if __name__ == "__main__":
    main()
