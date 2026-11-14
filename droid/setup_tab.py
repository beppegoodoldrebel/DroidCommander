"""'Setup' tab: microphone, droid audio output and master volume."""

import json
import math
import tkinter as tk
from tkinter import ttk

from . import theme, voices
from .settings_io import update_settings
from .sounds import default_device_name, find_device, list_devices

DEFAULT_IN = "Windows default"
DEFAULT_OUT = "Windows default (recommended)"


class SetupTab(ttk.Frame):
    def __init__(self, parent, editor):
        super().__init__(parent, padding=(14, 8))
        self.ed = editor
        self.dirty = False
        self._loading = True
        self._stream = None
        self._level = 0.0
        with open(editor.settings_path, "r", encoding="utf-8-sig") as f:
            s = json.load(f)
        snd = s.get("sound") or {}
        try:
            self.inputs = list_devices("input")
            self.outputs = list_devices("output")
        except Exception:                        # no audio system: keep the tab usable
            self.inputs, self.outputs = [], []
        C = theme.C

        # ---- microphone
        box = ttk.LabelFrame(self, text="Microphone — what the droid listens to", padding=10)
        box.pack(fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Input device:").pack(side="left")
        self.mic_var = tk.StringVar(value=self._label(s.get("microphone"), self.inputs, DEFAULT_IN))
        cb = ttk.Combobox(row, textvariable=self.mic_var, state="readonly", width=52,
                          values=[DEFAULT_IN] + [n for _, n in self.inputs])
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_mic())
        self.test_btn = ttk.Button(row, text="🎙 Test microphone", command=self.toggle_meter)
        self.test_btn.pack(side="left")
        meter = ttk.Frame(box)
        meter.pack(fill="x", pady=(10, 0))
        self.meter = tk.Canvas(meter, height=18, bg=C["field"], highlightthickness=1,
                               highlightbackground=C["border"])
        self.meter.pack(side="left", fill="x", expand=True)
        self.meter_info = ttk.Label(meter, text="", style="Hint.TLabel", width=34)
        self.meter_info.pack(side="left", padx=(10, 0))
        ttk.Label(box, style="Hint.TLabel", text=f"Windows default is currently: "
                  f"{default_device_name('input') or '?'}").pack(anchor="w", pady=(6, 0))

        # ---- activation: wake word and push-to-talk
        act = s.get("activation") or {}
        self.act = act
        ptt = act.get("push_to_talk") or {}
        self.triggers = [dict(t) for t in ptt.get("triggers", []) if t.get("enabled", True)]
        self._capture = None
        self._ptt_probe = None
        box = ttk.LabelFrame(self, text="Talking to the droid — how it listens", padding=10)
        box.pack(fill="x", pady=(10, 0))
        mode = "ptt" if ptt.get("enabled", False) and self.triggers else "always"
        self.mode_var = tk.StringVar(value=mode)
        ttk.Radiobutton(box, text="Always listening: commands start with the droid's name "
                                  "(“R2, open S-foils”)", value="always",
                        variable=self.mode_var, command=self.on_mode).pack(anchor="w")
        ttk.Radiobutton(box, text="Push-to-talk: listens only while one of these keys or buttons is held",
                        value="ptt", variable=self.mode_var, command=self.on_mode
                        ).pack(anchor="w", pady=(6, 0))
        self.ptt_frame = ttk.Frame(box)
        self.ptt_frame.pack(fill="x", padx=(24, 0))
        row = ttk.Frame(self.ptt_frame)
        row.pack(fill="x", pady=(6, 0))
        self.trig_list = tk.Listbox(row, height=4, width=52, activestyle="none", exportselection=False,
                                    bg=C["field"], fg=C["text"], selectbackground=C["amber"],
                                    selectforeground=C["bg"], highlightthickness=1,
                                    highlightbackground=C["border"], borderwidth=0)
        self.trig_list.pack(side="left")
        btns = ttk.Frame(row)
        btns.pack(side="left", padx=8, anchor="n")
        self.add_btn = ttk.Button(btns, text="＋ Add key or button", command=self.toggle_capture)
        self.add_btn.pack(fill="x")
        ttk.Button(btns, text="Remove", command=self.remove_trigger).pack(fill="x", pady=(4, 0))
        self.ptt_info = ttk.Label(row, text="", style="Hint.TLabel", width=40, wraplength=330,
                                  justify="left")
        self.ptt_info.pack(side="left", padx=(8, 0), anchor="n")
        self.require_var = tk.BooleanVar(value=ptt.get("require_wake_word", False))
        ttk.Checkbutton(self.ptt_frame, text="Require the droid's name too (“R2, open S-foils”)",
                        variable=self.require_var, command=self.mark_dirty).pack(anchor="w", pady=(6, 0))
        ttk.Label(self.ptt_frame, style="Hint.TLabel", text="Keyboard keys, mouse side/middle buttons, and "
                  "buttons or hats of any joystick, throttle or gamepad. Hold one here to test: its line "
                  "lights up.").pack(anchor="w", pady=(4, 0))
        self.fill_triggers()
        self.show_mode()

        # ---- output
        box = ttk.LabelFrame(self, text="Droid audio output — where the droid's voice plays", padding=10)
        box.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Output device:").pack(side="left")
        out_spec = snd.get("output_device") if snd.get("backend") == "sounddevice" else None
        self.out_var = tk.StringVar(value=self._label(out_spec, self.outputs, DEFAULT_OUT))
        cb = ttk.Combobox(row, textvariable=self.out_var, state="readonly", width=52,
                          values=[DEFAULT_OUT] + [n for _, n in self.outputs])
        cb.pack(side="left", padx=8)
        cb.bind("<<ComboboxSelected>>", lambda e: self.mark_dirty())
        ttk.Button(row, text="▶ Test", command=self.test_output).pack(side="left")
        ttk.Label(box, style="Hint.TLabel", wraplength=900, justify="left",
                  text=f"Windows default plays through Windows' own sound system (currently "
                       f"{default_device_name('output') or '?'}), which works on every PC. Pick a "
                       "specific device to send the droid somewhere else, for example to speakers "
                       "while the game uses your headset. If the test is silent, go back to "
                       "Windows default.").pack(anchor="w", pady=(6, 0))

        # ---- volume
        box = ttk.LabelFrame(self, text="Master volume — every droid sound", padding=10)
        box.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="🔊").pack(side="left")
        self.volume_var = tk.DoubleVar(value=round(self.ed.sounds.volume * 100))
        scale = ttk.Scale(row, from_=0, to=100, variable=self.volume_var, orient="horizontal", length=420,
                          command=lambda _v: self.volume_label.configure(text=f"{self.volume_var.get():.0f}%"))
        scale.pack(side="left", padx=8)
        scale.bind("<ButtonRelease-1>", lambda e: self.save_volume())
        self.volume_label = ttk.Label(row, text=f"{self.volume_var.get():.0f}%", width=5)
        self.volume_label.pack(side="left")
        ttk.Label(row, text="saved immediately; a running Droid Commander uses it right away",
                  style="Hint.TLabel").pack(side="left", padx=12)

        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", pady=(8, 0), before=self.winfo_children()[0])
        self.state_label = ttk.Label(bottom, text="", style="Hint.TLabel")
        self.state_label.pack(side="left")
        ttk.Button(bottom, text="Save", style="Accent.TButton", command=self.save).pack(side="right")
        # stop the meter when the tab is left (checked after idle: layout can unmap briefly)
        self.bind("<Unmap>", lambda e: self.after(200, self._stop_if_hidden))
        self._loading = False
        self.draw_meter()
        self.after(300, self.probe_ptt)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _label(spec, devices, default):
        if spec in (None, ""):
            return default
        idx = find_device(spec, "input" if default == DEFAULT_IN else "output")
        return next((n for i, n in devices if i == idx), default)

    def _index(self, label, devices):
        return next((i for i, n in devices if n == label), None)

    def mark_dirty(self):
        if self._loading:
            return
        self.dirty = True
        self.state_label.configure(text="● unsaved changes — used from the next LAUNCH!")

    def on_mic(self):
        self.mark_dirty()
        if self._stream is not None:              # restart the meter on the new device
            self.stop_meter()
            self.toggle_meter()

    # ---------------------------------------------------------- mic meter
    def toggle_meter(self):
        if self._stream is not None:
            self.stop_meter()
            return
        import sounddevice as sd
        idx = self._index(self.mic_var.get(), self.inputs)

        def callback(indata, frames, t, status):  # audio thread: only store a number
            rms = float((indata.astype("float32") ** 2).mean() ** 0.5) / 32768.0
            self._level = max(rms, self._level * 0.85)

        try:
            self._stream = sd.InputStream(device=idx, channels=1, samplerate=16000, dtype="int16",
                                          blocksize=800, callback=callback)
            self._stream.start()
        except Exception as e:
            self._stream = None
            self.meter_info.configure(text=f"⚠ can't open: {e}", style="Warn.TLabel")
            return
        self.test_btn.configure(text="■ Stop test")
        self.meter_info.configure(text="speak: the bar should move", style="Hint.TLabel")
        self.after(50, self.tick_meter)

    def _stop_if_hidden(self):
        if self.winfo_exists() and not self.winfo_viewable():
            self.stop_meter()
            self.stop_capture()

    # ------------------------------------------------------- push-to-talk
    def fill_triggers(self):
        from .triggers import trigger_label
        self.trig_list.delete(0, "end")
        for t in self.triggers:
            self.trig_list.insert("end", "  " + trigger_label(t))
        if not self.triggers:
            self.trig_list.insert("end", "  (none: press “Add key or button”)")
        self._ptt_probe = None                    # rebuilt by probe_ptt

    def show_mode(self):
        """Push-to-talk controls are only usable in push-to-talk mode."""
        state = "normal" if self.mode_var.get() == "ptt" else "disabled"

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, ttk.Label):       # hints stay as they are
                    continue
                try:
                    c.configure(state=state)
                except tk.TclError:
                    pass
                walk(c)
        walk(self.ptt_frame)
        if state == "disabled":
            self.stop_capture()

    def on_mode(self):
        self.mark_dirty()
        self.show_mode()
        if self.mode_var.get() == "ptt" and not self.triggers:
            self.toggle_capture()

    def toggle_capture(self):
        if self._capture is not None:
            self.stop_capture()
            return
        from .triggers import Capture
        try:
            self._capture = Capture()
        except Exception as e:
            self.ptt_info.configure(text=f"⚠ {e}", style="Warn.TLabel")
            return
        self._capture_until = self.tk.call("clock", "milliseconds") + 10000
        self.add_btn.configure(text="■ Cancel")
        self.ptt_info.configure(text="Press the key or button now…", style="Ok.TLabel")
        self.after(15, self.tick_capture)

    def stop_capture(self, message=""):
        self._capture = None
        if self.winfo_exists():
            self.add_btn.configure(text="＋ Add key or button")
            self.ptt_info.configure(text=message, style="Hint.TLabel")

    def tick_capture(self):
        if self._capture is None or not self.winfo_exists():
            return
        try:
            t = self._capture.poll()
        except Exception as e:
            self.stop_capture(f"⚠ {e}")
            return
        if t is None:
            if self.tk.call("clock", "milliseconds") > self._capture_until:
                self.stop_capture("Nothing pressed. Try again.")
            else:
                self.after(15, self.tick_capture)
            return
        from .triggers import trigger_label
        same = lambda a: {k: v for k, v in a.items() if k not in ("joy_id", "enabled")}
        if any(same(x) == same(t) for x in self.triggers):
            self.stop_capture(f"{trigger_label(t)} is already in the list.")
            return
        self.triggers.append(t)
        self.fill_triggers()
        self.mark_dirty()
        self.stop_capture(f"Added {trigger_label(t)}.")

    def remove_trigger(self):
        sel = self.trig_list.curselection()
        if not sel or sel[0] >= len(self.triggers):
            return
        del self.triggers[sel[0]]
        self.fill_triggers()
        self.mark_dirty()

    def probe_ptt(self):
        """Light up the list line of a held trigger, so it can be tested right here."""
        if not self.winfo_exists():
            return
        if (self.winfo_viewable() and self._capture is None and self.triggers
                and self.mode_var.get() == "ptt"):
            from .triggers import PushToTalk
            try:
                if self._ptt_probe is None:
                    self._ptt_probe = [PushToTalk([t]) for t in self.triggers]
                    shared = next((p.joys for p in self._ptt_probe if p.joys), None)
                    for p in self._ptt_probe:     # one controller scan for all lines
                        if p.joys:
                            p.joys = shared
                C = theme.C
                for i, p in enumerate(self._ptt_probe):
                    held = p._check()
                    self.trig_list.itemconfigure(i, background=C["ok"] if held else C["field"],
                                                 foreground=C["bg"] if held else C["text"])
            except Exception:
                self._ptt_probe = []
        self.after(50, self.probe_ptt)

    def stop_meter(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._level = 0.0
        if self.winfo_exists():
            self.test_btn.configure(text="🎙 Test microphone")
            self.meter_info.configure(text="", style="Hint.TLabel")
            self.draw_meter()

    def tick_meter(self):
        if self._stream is None or not self.winfo_exists():
            return
        self.draw_meter()
        db = 20 * math.log10(self._level + 1e-6)
        self.meter_info.configure(text="✓ hearing you" if db > -35 else "speak: the bar should move",
                                  style="Ok.TLabel" if db > -35 else "Hint.TLabel")
        self._level *= 0.9
        self.after(50, self.tick_meter)

    def draw_meter(self):
        C = theme.C
        cv = self.meter
        cv.delete("all")
        w = max(cv.winfo_width(), 300)
        db = 20 * math.log10(self._level + 1e-6)            # about -60 (silence) .. 0 dB
        frac = min(1.0, max(0.0, (db + 60) / 60))
        color = C["ok"] if frac < 0.75 else C["amber"] if frac < 0.92 else C["warn"]
        cv.create_rectangle(0, 0, w * frac, 20, fill=color, outline="")
        for x in range(1, 20):
            cv.create_line(w * x / 20, 0, w * x / 20, 20, fill=C["bg"])

    # -------------------------------------------------------------- output
    def output_config(self):
        """(backend, device name or None) for the chosen output."""
        label = self.out_var.get()
        if label == DEFAULT_OUT:
            return "winsound", None
        return "sounddevice", label

    def test_output(self):
        backend, name = self.output_config()
        snd = self.ed.sounds
        old = snd.backend, snd.device
        snd.backend, snd.device = backend, self._index(name, self.outputs) if name else None
        snd.play("ready")                        # playback starts now; restore the saved choice
        snd.backend, snd.device = old

    def save_volume(self):
        data = voices.load(self.ed.voices_path)
        data["volume"] = round(self.volume_var.get()) / 100
        voices.save(self.ed.voices_path, data)
        self.ed.set_status(f"Droid volume set to {self.volume_var.get():.0f}%.")
        self.ed.sounds.play("ack")

    # ---------------------------------------------------------------- save
    def save(self):
        with open(self.ed.settings_path, "r", encoding="utf-8-sig") as f:
            snd = dict(json.load(f).get("sound") or {})
        backend, out_name = self.output_config()
        snd["backend"], snd["output_device"] = backend, out_name
        use_ptt = self.mode_var.get() == "ptt"
        if use_ptt and not self.triggers:
            from tkinter import messagebox
            messagebox.showerror("Talking to the droid", "Add at least one push-to-talk key or button, "
                                 "or choose Always listening: otherwise the droid can't hear you.",
                                 parent=self)
            return False
        mic = None if self.mic_var.get() == DEFAULT_IN else self.mic_var.get()
        with open(self.ed.settings_path, "r", encoding="utf-8-sig") as f:
            act = dict(json.load(f).get("activation") or {})
        wake = dict(act.get("wake_word") or {})
        wake["enabled"] = not use_ptt
        ptt = dict(act.get("push_to_talk") or {})
        ptt["enabled"] = use_ptt
        ptt["require_wake_word"] = self.require_var.get()
        ptt.setdefault("preroll_ms", 300)
        ptt.setdefault("tail_ms", 300)
        ptt["triggers"] = [{k: v for k, v in t.items() if v is not None} for t in self.triggers]
        act["wake_word"], act["push_to_talk"] = wake, ptt
        update_settings(self.ed.settings_path, {"microphone": mic, "activation": act, "sound": snd})
        self.ed.sounds.backend = backend                    # previews in the editor follow too
        self.ed.sounds.device = self._index(out_name, self.outputs) if out_name else None
        self.dirty = False
        self.state_label.configure(text="")
        self.ed.set_status("Audio setup saved. It is used from the next LAUNCH!.")
        return True
