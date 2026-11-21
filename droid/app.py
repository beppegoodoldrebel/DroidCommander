"""Main voice loop: microphone -> Vosk -> command -> keys + droid sound."""

import collections
import json
import os
import queue
import threading
import time

from .bindings import BindingStore
from .executor import Executor, CommandError
from .paths import resolve_model
from . import gamelink
from .gamelink import GameLink, Reactions, answer, event_config, read_state
from .phrases import PhraseBook, missing_words, normalize, to_json
from .sounds import SoundBank, find_device
from .squad import (DEFAULT_WING_NAMES, SQUAD_SHORTCUTS, WING_PREFIX, is_squad_order,
                    recipient_actions, wing_label)
from .triggers import PushToTalk

SAMPLE_RATE = 16000
EVENT_PREFIX = "@@"
DEFAULT_MODEL = "models/vosk-model-small-en-us-0.15"
BLOCK = 1600  # 100 ms


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


class DroidApp:
    def __init__(self, settings, commands, verbose=False, commands_path=None, settings_path=None,
                 events=False):
        settings["model_path"] = resolve_model(settings.get("model_path", DEFAULT_MODEL))
        self.s = settings
        self.events = events
        self.verbose = verbose
        self.commands = commands["commands"]
        self.commands_path = commands_path
        self._commands_mtime = os.path.getmtime(commands_path) if commands_path else None
        self.settings_path = settings_path
        self._settings_mtime = os.path.getmtime(settings_path) if settings_path else None
        self.bindings = BindingStore.from_settings(settings)
        self.executor = Executor(self.bindings, settings.get("game", {}))
        gl = settings.get("game_link") or {}
        gamelink.MANUAL_MOD_DIR = gl.get("mod_dir") or None
        if gl.get("press_controls", True):
            from .luacmd import LuaControls       # press controls inside the game, keys as fallback
            self.executor.lua = LuaControls(lambda: self.bindings.players_dir)
        snd = settings.get("sound", {})
        self.sounds = SoundBank(snd.get("folder", "sounds"), snd.get("volume", 0.8),
                                snd.get("output_device"), snd.get("backend", "winsound"),
                                snd.get("voices_file", "config/voices.json"))
        self._known_wings = None                # wing names the speech model knows
        self.book = self.make_book()
        act = settings["activation"]
        self.wake_enabled = act["wake_word"].get("enabled", True)
        ptt = act["push_to_talk"]
        self.ptt_enabled = ptt.get("enabled", False)
        self.ptt_require_wake = ptt.get("require_wake_word", False)
        self.preroll_blocks = max(0, int(ptt.get("preroll_ms", 300) / 100))
        self.tail_blocks = max(0, int(ptt.get("tail_ms", 300) / 100))
        self.ptt = PushToTalk(ptt.get("triggers", [])) if self.ptt_enabled else None
        if self.ptt and self.ptt.active:    # one mode at a time: push-to-talk replaces always-on
            self.wake_enabled = False
        self.min_conf = settings.get("recognition", {}).get("min_confidence", 0.55)
        self.jobs = queue.Queue()
        self.name = settings["droid"].get("name", "R2")
        self.reactions = Reactions(event_config(settings))
        self.game_link = None
        self.last_hit = self.last_kill = 0.0

    # ------------------------------------------------------------------ setup
    def wing_names(self):
        """Wing names for "<name> wing, ...", without words the speech model doesn't know."""
        names = [normalize(n) for n in self.s.get("wing_names", DEFAULT_WING_NAMES) if normalize(n)]
        if self._known_wings is None or self._known_wings[0] != names:
            known = names
            if os.path.isdir(self.s["model_path"]):
                try:
                    missing = set(missing_words(self.s["model_path"], {w for n in names for w in n.split()}))
                    known = [n for n in names if not set(n.split()) & missing]
                    if missing:
                        print(f"  (wing names the speech model doesn't know, ignored: {', '.join(sorted(missing))})")
                except Exception:
                    pass
            self._known_wings = (names, known)
        return self._known_wings[1]

    def make_book(self):
        rec = self.s.get("recognition", {})
        return PhraseBook(self.commands, self.s["droid"]["wake_words"], fuzzy=rec.get("fuzzy_match", 0.75),
                          callsigns=self.s.get("callsigns"), wing_names=self.wing_names())

    def check(self):
        """Print problems with commands/bindings/vocabulary. Returns number of problems."""
        problems = 0
        for cmd in self.commands:
            try:
                self.executor.plan(cmd)
            except CommandError as e:
                problems += 1
                print(f"  ! {cmd['name']}: {e}")
        for phrase, a, b in self.book.duplicates:
            problems += 1
            print(f"  ! duplicate phrase '{phrase}' in '{a}' and '{b}'")
        if os.path.isdir(self.s["model_path"]):
            missing = missing_words(self.s["model_path"], self.book.all_words())
            for w in missing:
                problems += 1
                users = [c["name"] for c in self.commands
                         if any(w in normalize(p).split() for p in c.get("phrases", []))]
                where = ", ".join(users) if users else "wake word"
                print(f"  ! word '{w}' is unknown to the speech model ({where}): use a synonym")
        else:
            problems += 1
            print(f"  ! speech model not found in '{self.s['model_path']}' (run download_model.py)")
        return problems

    def _recognizer(self, model, grammar):
        from vosk import KaldiRecognizer
        rec = KaldiRecognizer(model, SAMPLE_RATE, to_json(grammar))
        rec.SetWords(True)
        return rec

    def emit(self, kind, **data):
        """Machine-readable event line for the launcher window (only with --events)."""
        if self.events:
            print(EVENT_PREFIX + json.dumps({"type": kind, **data}, ensure_ascii=False), flush=True)

    # ------------------------------------------------------------ recognition
    def handle_result(self, raw, source):
        res = json.loads(raw)
        text = res.get("text", "").strip()
        if not text or text == "[unk]":
            if source == "ptt":
                self.say("unknown", "[ptt] heard nothing")
            return
        words = [w for w in res.get("result", []) if w.get("word") != "[unk]"]
        conf = sum(w["conf"] for w in words) / len(words) if words else 0.0
        cmd, group, rest, score = self.book.match_full(text)
        had_wake = group is not None
        if source == "wake" and not had_wake:
            if self.verbose:
                print(f"  [wake] ignored (no droid name): \"{text}\"")
            return
        if source == "ptt" and self.ptt_require_wake and not had_wake:
            return
        tag = f"[{source}] \"{text}\" (conf {conf:.2f}, match {score:.2f})"
        self.emit("heard", text=text, conf=round(conf, 2), source=source, to=wing_label(group))
        if cmd is None:
            self.emit("unknown", text=text)
            self.say("unknown", f"{tag} -> not understood")
            return
        if conf < self.min_conf:
            self.emit("unknown", text=text, reason="low confidence")
            self.say("unknown", f"{tag} -> confidence too low for '{cmd['name']}'")
            return
        print(f"{tag} -> {cmd['name']}" + (f" (to {wing_label(group)})" if group and group.startswith(WING_PREFIX) else ""))
        self.jobs.put((cmd, group))

    def say(self, mood, message=None):
        if message:
            print(message)
        self.reactions.command_answered()
        self.sounds.play(mood)

    # ------------------------------------------------------------ game link
    def on_game_event(self, event, detail):
        """An event from the game (kill, hit...): maybe react with a droid sound."""
        if event in ("hit_hull", "hit_shield", "collision"):
            self.last_hit = time.time()
        elif event in ("kill", "kill_capital"):
            self.last_kill = time.time()
        response = self.reactions.pick(event)
        if response:
            self.sounds.play(response)
        self.emit("game", event=event, detail=detail, response=response)
        if self.verbose or response:
            print(f"[game] {event} {detail}" + (f" -> {response}" if response else ""))

    def answer_question(self, cmd, question):
        state = read_state(self.bindings.players_dir)
        response, why = answer(question, state, self.last_hit, self.last_kill)
        self.reactions.command_answered()
        self.sounds.play(response)
        print(f"  ? {cmd['name']}: {response} ({why})")
        self.emit("answer", name=cmd["name"], question=question, response=response, why=why)

    def on_link_status(self, state, path):
        self.emit("link", state=state, path=path)
        print(f"Game link: {state}" + (f" ({path})" if path else ""))

    def start_game_link(self):
        gl = self.s.get("game_link") or {}
        gamelink.MANUAL_MOD_DIR = gl.get("mod_dir") or None
        if not gl.get("enabled", True) or not (self.bindings.players_dir or gamelink.user_roots(None)):
            self.emit("link", state="off", path=None)
            return
        self.game_link = GameLink(self.bindings.players_dir, self.on_game_event, self.on_link_status)
        self.game_link.start()

    def _worker(self):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            cmd, group = job
            question = next((a["ask"] for a in cmd.get("actions", []) if "ask" in a), None)
            if question:                        # a question: answer from the ship's state
                self.answer_question(cmd, question)
                continue
            try:
                ex = self.executor
                if is_squad_order(cmd) and self.squad_order_via_lua(cmd, group):
                    pass                        # sent through the game's comm menu functions
                else:
                    if is_squad_order(cmd):     # pick the recipient in the comm menu with keys
                        state = read_state(self.bindings.players_dir)
                        try:
                            extra = recipient_actions(group, state)
                        except ValueError as e:
                            raise CommandError(str(e))
                        cmd = dict(cmd, actions=list(cmd.get("actions", [])) + extra)
                    ex.execute(cmd)
                if ex.last_route == "game link":
                    print(f"  via game link: {ex.last_note}")
                elif ex.lua is not None and ex.last_note and self.verbose:
                    print(f"  keys (game link not used: {ex.last_note})")
                self.emit("command", name=cmd["name"], ok=True, route=ex.last_route)
                self.reactions.command_answered()
                self.sounds.play(cmd.get("sound", "ack"))
            except CommandError as e:
                self.emit("command", name=cmd["name"], ok=False, error=str(e))
                self.say("error", f"  ! {cmd['name']}: {e}")
            except Exception as e:
                self.emit("command", name=cmd["name"], ok=False, error=str(e))
                self.say("error", f"  ! unexpected error: {e}")

    def squad_order_via_lua(self, cmd, group):
        """Send a wingman order through the game link. True if done; raises CommandError if the
        game refused it (no such wing...); False to fall back to keys (no game link, no answer)."""
        lua = self.executor.lua
        if lua is None:
            return False
        shortcut = next(a["bind"] for a in cmd["actions"] if a.get("bind") in SQUAD_SHORTCUTS)
        wing = group[len(WING_PREFIX):] if group and group.startswith(WING_PREFIX) else None
        ok, note = lua.send_order(shortcut, wing)
        self.executor.last_note = note
        if ok:
            self.executor.last_route = "game link"
            return True
        if lua.answered:                        # the game itself said no: keys wouldn't do better
            raise CommandError(note)
        return False

    def _reload_settings(self):
        """Pick up a new droid name / wake words / PTT name requirement from settings.json."""
        if not self.settings_path:
            return False
        try:
            mtime = os.path.getmtime(self.settings_path)
            if mtime == self._settings_mtime:
                return False
            self._settings_mtime = mtime
            new = load_json(self.settings_path)
            droid = new["droid"]
            require = new["activation"]["push_to_talk"].get("require_wake_word", False)
        except (OSError, ValueError, KeyError) as e:
            print(f"  ! could not reload settings: {e}")
            return False
        keys = ("bindings_file", "fso_players_dir", "pilot", "follow_pilot")
        if any(new.get(k) != self.s.get(k) for k in keys):      # game controls preset changed
            for k in keys:
                self.s[k] = new.get(k)
            try:
                b = self.bindings
                fresh = type(b).from_settings(self.s)
                b.configure(fresh.fixed_path, fresh.players_dir, fresh.pilot, fresh.follow_pilot)
                print(f"Game controls: now using {b.preset_name}"
                      + (f" (follows pilot {b.pilot})" if b.follow_pilot else "") + ".")
            except (OSError, ValueError) as e:
                print(f"  ! could not load the new preset: {e}")
        if new.get("events") != self.s.get("events"):            # event reactions edited
            self.s["events"] = new.get("events")
            self.reactions.config = event_config(self.s)
            print("Event reactions reloaded.")
        callsigns = new.get("callsigns") or {}
        if new.get("wing_names") != self.s.get("wing_names"):
            self.s["wing_names"] = new.get("wing_names")
            print("Wing names reloaded.")
            if droid == self.s["droid"] and require == self.ptt_require_wake:
                return True
        if droid == self.s["droid"] and require == self.ptt_require_wake and callsigns == (self.s.get("callsigns") or {}):
            return False
        if callsigns != (self.s.get("callsigns") or {}):
            self.s["callsigns"] = callsigns
            print("Callsigns: " + "; ".join(f"{k} ({', '.join(v)})" for k, v in callsigns.items()))
        self.s["droid"] = droid
        self.name = droid.get("name", self.name)
        self.ptt_require_wake = require
        print(f"Droid name is now “{self.name}” (accepted as: {', '.join(droid['wake_words'])}).")
        return True

    def _reload_commands(self):
        if not self.commands_path:
            return False
        try:
            mtime = os.path.getmtime(self.commands_path)
            if mtime == self._commands_mtime:
                return False
            self._commands_mtime = mtime
            commands = load_json(self.commands_path)["commands"]
        except (OSError, ValueError, KeyError) as e:
            print(f"  ! could not reload commands: {e}")
            return False
        self.commands = commands
        print(f"Commands reloaded ({len(self.commands)} commands).")
        return True

    def config_changed(self):
        """Reload settings.json / commands.json if the editor saved them. True if anything changed."""
        changed = self._reload_settings()
        changed = self._reload_commands() or changed
        if changed:
            self.book = self.make_book()
        return changed

    def emit_ready(self, modes, reloaded=False):
        b = self.bindings
        self.emit("ready", name=self.name, modes=modes, reloaded=reloaded,
                  callsigns=list((self.s.get("callsigns") or {}).keys()),
                  preset=b.preset_name, pilot=b.pilot if b.follow_pilot else None,
                  voice=self.sounds.voices.data.get("active"), commands=len(self.commands))

    # ------------------------------------------------------------------- loop
    def run(self):
        import sounddevice as sd
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        self.emit("status", text="Checking commands")
        print("Checking commands...")
        if self.check() == 0:
            print("  all good")
        print(f"Loading speech model from {self.s['model_path']} ...")
        self.emit("status", text="Loading speech model")
        model = Model(self.s["model_path"])

        def build_recognizers():
            w = p = None
            if self.wake_enabled:
                w = self._recognizer(model, self.book.grammar(with_wake=True, without_wake=False))
            if self.ptt:
                p = self._recognizer(model, self.book.grammar(
                    with_wake=True, without_wake=not self.ptt_require_wake))
            return w, p

        wake_rec, ptt_rec = build_recognizers()
        if self.ptt:
            self.ptt.start()
        if not wake_rec and not (self.ptt and self.ptt.active):
            print("No activation mode enabled: check config/settings.json")
            self.emit("fatal", text="No activation mode enabled")
            return

        threading.Thread(target=self._worker, daemon=True).start()
        self.start_game_link()
        audio = queue.Queue()

        def callback(indata, frames, t, status):
            audio.put(bytes(indata))

        preroll = collections.deque(maxlen=self.preroll_blocks)
        ptt_active = ptt_handled = False
        tail = 0
        blocks = 0

        modes = []
        if wake_rec:
            modes.append(f"wake word ({', '.join(self.book.wake_words)})")
        if self.ptt and self.ptt.active:
            modes.append("push-to-talk")
        mic = find_device(self.s.get("microphone"), "input")
        print(f"Microphone: {self.s.get('microphone') or 'Windows default'}")
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK, dtype="int16",
                               channels=1, device=mic, callback=callback):
            print(f"{self.name} is listening: {' + '.join(modes)}. Ctrl+C to quit.")
            self.emit_ready(modes)
            self.sounds.play("ready")
            try:
                while True:
                    data = audio.get()
                    pressed = self.ptt.is_pressed() if self.ptt else False

                    blocks += 1      # every ~2 s, outside a push-to-talk utterance
                    if blocks % 20 == 0 and not ptt_active and not pressed and self.config_changed():
                        wake_rec, ptt_rec = build_recognizers()
                        self.emit_ready(modes, reloaded=True)
                        self.sounds.play("chatter")

                    if pressed and not ptt_active:          # PTT pressed
                        ptt_active, ptt_handled, tail = True, False, self.tail_blocks
                        self.emit("ptt", down=True)
                        ptt_rec.Reset()
                        for b in preroll:
                            ptt_rec.AcceptWaveform(b)
                        if self.verbose:
                            print("  [ptt] listening...")
                    if ptt_active:
                        if ptt_rec.AcceptWaveform(data):     # pause inside the press
                            r = ptt_rec.Result()
                            if json.loads(r).get("text", "[unk]") != "[unk]":
                                self.handle_result(r, "ptt")
                                ptt_handled = True
                        if not pressed:
                            tail -= 1
                            if tail <= 0:
                                ptt_active = False
                                self.emit("ptt", down=False)
                                r = ptt_rec.FinalResult()
                                if not (ptt_handled and not json.loads(r).get("text")):
                                    self.handle_result(r, "ptt")
                                ptt_rec.Reset()
                        if wake_rec:
                            wake_rec.Reset()
                    elif wake_rec:
                        if wake_rec.AcceptWaveform(data):
                            self.handle_result(wake_rec.Result(), "wake")
                        elif self.verbose:
                            p = json.loads(wake_rec.PartialResult()).get("partial")
                            if p:
                                print(f"  ... {p}", end="\r")
                    preroll.append(data)
            except KeyboardInterrupt:
                print("\nGoodbye!")
            finally:
                self.jobs.put(None)
                if self.game_link:
                    self.game_link.stop()
                if self.ptt:
                    self.ptt.stop()
