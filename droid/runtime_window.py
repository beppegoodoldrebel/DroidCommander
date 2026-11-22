"""The ACTIVE view shown while Droid Commander runs (the app's LAUNCH! mode).

Droid Commander runs as a separate process (`python -m droid --events run`); its event lines
(prefixed with @@) drive the status display, everything else goes to the log.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

from . import theme
from .paths import engine_command
from .settings_io import update_settings

EVENT_PREFIX = "@@"


class RuntimePanel(tk.Frame):
    """Status lamp, configuration, last heard/command and log of a running Droid Commander."""

    def __init__(self, master, settings_path, commands_path, on_stopped):
        super().__init__(master, bg=theme.C["bg"])
        C = theme.C
        self.C = C
        self.settings_path = settings_path
        self.commands_path = commands_path
        self.on_stopped = on_stopped
        self.proc = None
        self.lines = queue.Queue()
        self.run_state = "starting"
        self.ptt_down = False
        self._pulse = False
        self._stopping = False

        bottom = tk.Frame(self, bg=C["panel"])
        bottom.pack(side="bottom", fill="x")
        self.stop_btn = ttk.Button(bottom, text="■  Stop · Configure", style="Accent.TButton", command=self.stop)
        self.stop_btn.pack(side="right", padx=10, pady=8)
        ttk.Button(bottom, text="▁  Minimize", command=self.minimize).pack(side="right", pady=8)
        self.foot = tk.Label(bottom, text="", bg=C["panel"], fg=C["cyan"], font=C["F"]["mono"], anchor="w")
        self.foot.pack(side="left", fill="x", padx=12)

        self.ask_bar = None
        try:
            with open(settings_path, "r", encoding="utf-8-sig") as f:
                choice = json.load(f).get("launch_window")
        except (OSError, ValueError):
            choice = None
        if choice == "minimize":
            self.after(400, self.minimize)
        elif choice != "keep":
            self._build_ask_bar()

        body = ttk.Frame(self, padding=(12, 10))
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")

        # status lamp
        lamp_box = ttk.LabelFrame(top, text="Status", padding=10)
        lamp_box.pack(side="left", fill="y")
        self.lamp = tk.Canvas(lamp_box, width=120, height=120, bg=C["bg"], highlightthickness=0)
        self.lamp.pack()
        self.state_label = tk.Label(lamp_box, text="STARTING", bg=C["bg"], fg=C["amber"],
                                    font=(C["F"]["head"][0], 14))
        self.state_label.pack(pady=(6, 0))
        self.state_sub = tk.Label(lamp_box, text="loading the speech model…", bg=C["bg"], fg=C["dim"],
                                  font=C["F"]["body"])
        self.state_sub.pack()

        # info
        info = ttk.LabelFrame(top, text="Configuration", padding=10)
        info.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.fields = {}
        for row, (key, label) in enumerate((("name", "Droid"), ("callsigns", "Callsigns"),
                                            ("voice", "Voice"),
                                            ("modes", "Listening"), ("commands", "Commands"),
                                            ("link", "Game link"))):
            tk.Label(info, text=label.upper(), bg=C["bg"], fg=C["dim"], font=C["F"]["sub"]).grid(
                row=row, column=0, sticky="w", pady=2)
            v = tk.Label(info, text="—", bg=C["bg"], fg=C["text"], font=C["F"]["body"], anchor="w",
                         justify="left", wraplength=520)
            v.grid(row=row, column=1, sticky="w", padx=(12, 0), pady=2)
            self.fields[key] = v

        # last heard / last command
        last = ttk.Frame(body)
        last.pack(fill="x", pady=(10, 0))
        hb = ttk.LabelFrame(last, text="Last heard", padding=8)
        hb.pack(side="left", fill="both", expand=True)
        self.heard = tk.Label(hb, text="—", bg=C["bg"], fg=C["cyan"], font=(C["F"]["head"][0], 13),
                              anchor="w", wraplength=380, justify="left")
        self.heard.pack(fill="x")
        cb = ttk.LabelFrame(last, text="Last command", padding=8)
        cb.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.last_cmd = tk.Label(cb, text="—", bg=C["bg"], fg=C["text"], font=(C["F"]["head"][0], 13),
                                 anchor="w", wraplength=380, justify="left")
        self.last_cmd.pack(fill="x")

        # log
        lb = ttk.LabelFrame(body, text="Log", padding=6)
        lb.pack(fill="both", expand=True, pady=(10, 0))
        self.log = tk.Text(lb, height=8, wrap="word", state="disabled")
        theme.style_text(self.log)
        self.log.configure(font=C["F"]["mono"], fg=C["dim"])
        self.log.tag_configure("ok", foreground=C["ok"])
        self.log.tag_configure("warn", foreground=C["warn"])
        self.log.tag_configure("info", foreground=C["cyan"])
        sb = ttk.Scrollbar(lb, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        theme.polish(self)

        self.draw_lamp()
        self.start()
        self.after(100, self.poll)
        self.after(500, self.pulse)

    def minimize(self):
        self.winfo_toplevel().iconify()

    # ------------------------------------------------------------ decision
    def _build_ask_bar(self):
        C = self.C
        bar = tk.Frame(self, bg=C["amber_dark"], highlightthickness=1, highlightbackground=C["amber"])
        bar.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(bar, text="Minimize Droid Commander to the taskbar? It keeps listening.",
                 bg=C["amber_dark"], fg=C["amber"], font=C["F"]["head"]).pack(side="left", padx=10, pady=8)
        self.remember = tk.BooleanVar(value=False)
        tk.Checkbutton(bar, text="Remember my choice", variable=self.remember, bg=C["amber_dark"],
                       fg=C["text"], selectcolor=C["field"], activebackground=C["amber_dark"],
                       activeforeground=C["amber"], font=C["F"]["body"]).pack(side="right", padx=10)
        ttk.Button(bar, text="Keep open", command=lambda: self.decide("keep")).pack(side="right", pady=6)
        ttk.Button(bar, text="Minimize", style="Accent.TButton",
                   command=lambda: self.decide("minimize")).pack(side="right", padx=6, pady=6)
        self.ask_bar = bar

    def decide(self, choice):
        if self.remember.get():
            try:
                update_settings(self.settings_path, {"launch_window": choice})
            except (OSError, ValueError):
                pass
        self.ask_bar.destroy()
        self.ask_bar = None
        if choice == "minimize":
            self.minimize()

    # ------------------------------------------------------------- process
    def start(self):
        cmd = engine_command("--settings", self.settings_path, "--commands", self.commands_path,
                             "--events", "run")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        self.write(f"Starting: {' '.join(cmd[2:])}", "info")
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     errors="replace", env=env, cwd=os.getcwd(),
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):                      # background thread: never touch tkinter here
        for line in self.proc.stdout:
            self.lines.put(line.rstrip("\n"))
        self.lines.put(None)

    def poll(self):
        try:
            while True:
                line = self.lines.get_nowait()
                if line is None:
                    self.on_exit()
                    return
                self.handle_line(line)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self.poll)

    def stop(self):
        if self._stopping:
            return
        self._stopping = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.destroy()
        self.on_stopped()

    def on_exit(self):
        code = self.proc.poll()
        if self._stopping:
            return
        self.set_state("stopped", "Droid Commander has stopped" + (f" (exit code {code})" if code else ""))
        self.write("Droid Commander stopped." if not code else f"Droid Commander exited with code {code}.",
                   "warn" if code else "info")
        self.stop_btn.configure(text="✎  Back to configure")   # keep the log visible until then

    # -------------------------------------------------------------- events
    def write(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S  ") + text + "\n", tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def handle_line(self, line):
        if not line.startswith(EVENT_PREFIX):
            if line.strip():
                self.write(line.strip(), "warn" if line.strip().startswith("!") else None)
            return
        try:
            ev = json.loads(line[len(EVENT_PREFIX):])
        except ValueError:
            return
        t = ev.get("type")
        if t == "status":
            self.set_state("starting", ev.get("text", "").lower() + "…")
        elif t == "ready":
            self.fields["name"].configure(text=ev.get("name", "—"))
            self.fields["callsigns"].configure(text=", ".join(ev.get("callsigns") or []) or "—")
            self.fields["voice"].configure(text=ev.get("voice") or "—")
            self.fields["modes"].configure(text=" + ".join(ev.get("modes") or []) or "—")
            self.fields["commands"].configure(text=str(ev.get("commands", "—")))
            self.set_state("listening", f"say “{ev.get('name', 'R2')}, …”")
            self.write("Configuration reloaded." if ev.get("reloaded") else
                       f"{ev.get('name')} is listening.", "info")
        elif t == "ptt":
            self.ptt_down = bool(ev.get("down"))
            self.set_state("listening", "push-to-talk held" if self.ptt_down else
                           f"say “{self.fields['name'].cget('text')}, …”")
        elif t == "heard":
            to = ev.get("to")
            self.heard.configure(text=f"“{ev.get('text', '')}”")
            self.foot.configure(text=f"heard ({ev.get('source')}, conf {ev.get('conf')})"
                                + (f" → {to}" if to else ""))
        elif t == "unknown":
            self.last_cmd.configure(text="?  not understood", fg=self.C["warn"])
            self.write(f"Not understood: “{ev.get('text', '')}”"
                       + (f" ({ev['reason']})" if ev.get("reason") else ""), "warn")
        elif t == "command":
            if ev.get("ok"):
                self.last_cmd.configure(text=f"✓  {ev.get('name')}", fg=self.C["ok"])
                self.write(f"Executed: {ev.get('name')}", "ok")
            else:
                self.last_cmd.configure(text=f"⚠  {ev.get('name')}", fg=self.C["warn"])
                self.write(f"{ev.get('name')}: {ev.get('error')}", "warn")
        elif t == "answer":
            resp = ev.get("response")
            good = resp in ("positive", "victory")
            icon = "👍" if good else "?" if resp == "unknown" else "👎"
            color = self.C["ok"] if good else self.C["dim"] if resp == "unknown" else self.C["warn"]
            self.last_cmd.configure(text=f"{icon}  {ev.get('name')}", fg=color)
            self.write(f"{ev.get('name')}: {resp} — {ev.get('why')}", "ok" if good else "warn")
        elif t == "link":
            state = ev.get("state")
            text, color = {"connected": ("● connected — the droid reacts to game events", self.C["ok"]),
                           "waiting": ("○ waiting for the game (start a mission)", self.C["dim"]),
                           "off": ("off", self.C["dim"])}.get(state, (state, self.C["text"]))
            self.fields["link"].configure(text=text, fg=color)
            if state == "connected":
                self.write("Game link connected.", "info")
        elif t == "game":
            event, detail, resp = ev.get("event"), ev.get("detail") or "", ev.get("response")
            nice = event.replace("_", " ")
            what = detail.split("|")[-1] if detail else ""
            self.fields["link"].configure(text="● connected — the droid reacts to game events", fg=self.C["ok"])
            self.write(f"Game: {nice}" + (f" ({what})" if what else "")
                       + (f"  → droid: {resp}" if resp else ""), "ok" if resp else None)
            self.foot.configure(text=f"game event: {nice}" + (f" → {resp}" if resp else ""))
        elif t == "fatal":
            self.write(ev.get("text", "error"), "warn")

    # ---------------------------------------------------------------- lamp
    def set_state(self, state, sub=""):
        self.run_state = state
        labels = {"starting": ("STARTING", self.C["amber"]), "listening": ("LISTENING", self.C["ok"]),
                  "stopped": ("STOPPED", self.C["warn"])}
        text, color = labels.get(state, (state.upper(), self.C["text"]))
        if state == "listening" and self.ptt_down:
            text, color = "PUSH-TO-TALK", self.C["cyan"]
        self.state_label.configure(text=text, fg=color)
        self.state_sub.configure(text=sub)
        self.draw_lamp()

    def draw_lamp(self):
        C = self.C
        cv = self.lamp
        cv.delete("all")
        color = {"starting": C["amber"], "listening": C["ok"], "stopped": C["warn"]}.get(self.run_state, C["dim"])
        if self.run_state == "listening" and self.ptt_down:
            color = C["cyan"]
        glow = color if self._pulse or self.run_state != "listening" else C["border"]
        cv.create_oval(6, 6, 114, 114, outline=glow, width=3)
        cv.create_oval(22, 22, 98, 98, outline=C["border"], width=2, fill=C["panel"])
        cv.create_oval(40, 40, 80, 80, outline="", fill=color)

    def pulse(self):
        if not self.winfo_exists():
            return
        self._pulse = not self._pulse
        self.draw_lamp()
        self.after(600, self.pulse)
