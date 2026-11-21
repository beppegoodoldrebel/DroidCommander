"""'Test all' window of the Commands tab: try every command through the game link at once.

- Check names: asks the game which controls it knows. Presses nothing.
- Press all: presses each command, one every few seconds, while you watch the game.
Both need a mission running (a practice mission is best) with the game link installed.
"""

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from . import theme
from .luacmd import LuaControls, can_run
from .squad import SQUAD_SHORTCUTS, is_squad_order

COUNTDOWN = 5          # seconds to switch to the game window (FSO pauses when it loses focus)
GAP = 2.0              # seconds between two commands in "Press all"
# never pressed by "Press all": they end the test (jump out of the mission, wingmen leave)
NOT_IN_PRESS_ALL = {"END_MISSION": "would end the mission", "WARP_MESSAGE": "wingmen would leave"}


def kind_of(cmd):
    """('question'|'order'|'controls'|'keys', [control names])."""
    actions = cmd.get("actions", [])
    if any("ask" in a for a in actions):
        return "question", []
    if is_squad_order(cmd):
        return "order", [next(a["bind"] for a in actions if a.get("bind") in SQUAD_SHORTCUTS)]
    if can_run(cmd):
        return "controls", [a["bind"] for a in actions]
    return "keys", []


class TestAllDialog(tk.Toplevel):
    def __init__(self, editor):
        super().__init__(editor.root)
        self.ed = editor
        self.title("Test all commands")
        self.configure(bg=theme.C["bg"])
        self.geometry("980x640")
        self.transient(editor.root)
        self.lua = LuaControls(lambda: editor.bindings.players_dir)
        self.results = queue.Queue()
        self.stop_flag = threading.Event()
        self.running = False
        self.commands = [c for c in editor.commands if c.get("enabled", True)]

        top = ttk.Frame(self, padding=(14, 10))
        top.pack(fill="x")
        ttk.Label(top, style="Hint.TLabel", wraplength=940, justify="left", text=(
            "Start a mission and keep it running (a practice mission is best, the commands really "
            "happen). After you press a button you have 5 seconds to click into the game window: "
            "FreeSpace Open pauses when it isn't in front.\n"
            "• Check names — asks the game which controls it knows. Presses nothing.\n"
            "• Press all — presses each command through the game link, one every 2 seconds: watch "
            "the game and the Result column. Commands that would end the test (jump to hyperspace, "
            "wingmen depart) are skipped.")).pack(anchor="w")
        row = ttk.Frame(top)
        row.pack(fill="x", pady=(8, 0))
        self.check_btn = ttk.Button(row, text="Check names", command=lambda: self.start("check"))
        self.check_btn.pack(side="left")
        self.press_btn = ttk.Button(row, text="Press all", style="Accent.TButton", command=lambda: self.start("press"))
        self.press_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(row, text="■ Stop", command=self.stop_flag.set, state="disabled")
        self.stop_btn.pack(side="left")
        self.orders_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Include wingman orders (sent to all fighters)",
                        variable=self.orders_var).pack(side="left", padx=16)
        self.status = ttk.Label(row, text="", style="Hint.TLabel")
        self.status.pack(side="right")

        box = ttk.Frame(self, padding=(14, 0, 14, 10))
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(box, columns=("cmd", "actions", "result"), show="headings")
        for col, text, width in (("cmd", "Command", 230), ("actions", "Game controls", 260), ("result", "Result", 420)):
            self.tree.heading(col, text=text, anchor="w")
            self.tree.column(col, width=width, anchor="w")
        sb = ttk.Scrollbar(box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        C = theme.C
        for tag, color in (("ok", C["ok"]), ("bad", C["warn"]), ("info", C["dim"]), ("now", C["amber"])):
            self.tree.tag_configure(tag, foreground=color)
        self.rows = {}
        for i, cmd in enumerate(self.commands):
            kind, names = kind_of(cmd)
            text = {"question": "question (no controls)", "keys": "fixed keys / mouse (keyboard only)"}.get(kind, "")
            self.rows[i] = self.tree.insert("", "end", values=(cmd["name"], ", ".join(names), text),
                                            tags=("info",) if text else ())
        self.summary = ttk.Label(self, text="", padding=(14, 0, 14, 10))
        self.summary.pack(fill="x")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.poll)

    # ------------------------------------------------------------ running
    def set_row(self, i, text, tag):
        if self.winfo_exists():
            vals = self.tree.item(self.rows[i], "values")
            self.tree.item(self.rows[i], values=(vals[0], vals[1], text), tags=(tag,))
            if tag == "now":
                self.tree.see(self.rows[i])

    def start(self, what):
        if self.running:
            return
        self.running = True
        self.stop_flag.clear()
        for b in (self.check_btn, self.press_btn):
            b.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        include_orders = self.orders_var.get()
        threading.Thread(target=self.work, args=(what, include_orders), daemon=True).start()

    def work(self, what, include_orders):          # background thread: never touch tkinter here
        put = self.results.put
        for n in range(COUNTDOWN, 0, -1):
            if self.stop_flag.is_set():
                put(("done", "Stopped.")); return
            put(("status", f"Switch to the game… {n}"))
            time.sleep(1)
        if what == "check":
            self.do_check(put)
        else:
            self.do_press(put, include_orders)

    def do_check(self, put):
        names = set()
        for cmd in self.commands:
            names.update(kind_of(cmd)[1])
        put(("status", "Asking the game…"))
        try:
            known, unknown = self.lua.check(names)
        except RuntimeError as e:
            put(("done", f"⚠ The game didn't answer: {e}. Is a mission running, not paused, with the "
                         "game link installed (Events tab)?"))
            return
        good = bad = 0
        for i, cmd in enumerate(self.commands):
            kind, cmd_names = kind_of(cmd)
            if not cmd_names:
                continue
            missing = [n for n in cmd_names if n in unknown]
            if missing:
                bad += 1
                put(("row", i, f"✗ unknown to the game: {', '.join(missing)} (will use keys)", "bad"))
            else:
                good += 1
                put(("row", i, "✓ the game knows it", "ok"))
        put(("done", f"{good} command(s) can go through the game link, {bad} can't."))

    def do_press(self, put, include_orders):
        good = bad = skipped = 0
        for i, cmd in enumerate(self.commands):
            if self.stop_flag.is_set():
                put(("done", f"Stopped. {good} worked, {bad} failed.")); return
            kind, names = kind_of(cmd)
            risky = next((NOT_IN_PRESS_ALL[n] for n in names if n in NOT_IN_PRESS_ALL), None)
            if risky:
                put(("row", i, f"skipped ({risky}: test it by hand)", "info"))
                skipped += 1
                continue
            if kind in ("question", "keys") or (kind == "order" and not include_orders):
                if kind == "order":
                    put(("row", i, "skipped (wingman order)", "info"))
                skipped += 1
                continue
            put(("row", i, "▶ pressing now — watch the game", "now"))
            put(("status", f"{cmd['name']}…"))
            if kind == "order":
                shortcut = kind_of(cmd)[1][0]
                ok, note = self.lua.send_order(shortcut, None)
            else:
                ok, note = self.lua.send(cmd)
            if ok:
                good += 1
                put(("row", i, f"✓ pressed via game link ({note})", "ok"))
            else:
                bad += 1
                put(("row", i, f"✗ {note}", "bad"))
                if not self.lua.answered and "no mission" in note:
                    put(("done", "⚠ No mission running with the game link (or the game is paused). "
                                 "Start a mission, then try again.")); return
            for _ in range(int(GAP * 10)):
                if self.stop_flag.is_set():
                    break
                time.sleep(0.1)
        put(("done", f"Done: {good} worked, {bad} failed, {skipped} skipped."))

    def poll(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                msg = self.results.get_nowait()
                if msg[0] == "row":
                    self.set_row(msg[1], msg[2], msg[3])
                elif msg[0] == "status":
                    self.status.configure(text=msg[1])
                elif msg[0] == "done":
                    self.status.configure(text="")
                    self.summary.configure(text=msg[1])
                    self.running = False
                    for b in (self.check_btn, self.press_btn):
                        b.state(["!disabled"])
                    self.stop_btn.state(["disabled"])
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def close(self):
        self.stop_flag.set()
        self.destroy()
