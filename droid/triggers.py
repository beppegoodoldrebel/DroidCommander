"""Push-to-talk triggers: any keyboard/mouse key, joystick/gamepad button or POV hat.

Uses GetAsyncKeyState and winmm joyGetPosEx, both of which work while the
game window has focus (no hooks, no extra dependencies).
"""

import ctypes
import threading
import time
from ctypes import wintypes

from .keymap import FSO_SCANCODES, SCANCODE_TO_NAME

user32 = ctypes.WinDLL("user32")
winmm = ctypes.WinDLL("winmm")

MAPVK_VK_TO_VSC_EX = 4
MAPVK_VSC_TO_VK_EX = 3

MOUSE_VK = {"MOUSE_LEFT": 0x01, "MOUSE_RIGHT": 0x02, "MOUSE_MIDDLE": 0x04,
            "MOUSE_X1": 0x05, "MOUSE_X2": 0x06}
VK_TO_MOUSE = {v: k for k, v in MOUSE_VK.items()}
# Generic VKs we skip in learn mode (the left/right specific ones are reported instead)
GENERIC_VK = {0x10, 0x11, 0x12}
# Navigation keys share scancodes with the numpad; their VKs are always the extended ones
EXTENDED_VK = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x6F, 0xA3, 0xA5}


class JOYINFOEX(ctypes.Structure):
    _fields_ = [(n, wintypes.DWORD) for n in (
        "dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos", "dwUpos",
        "dwVpos", "dwButtons", "dwButtonNumber", "dwPOV", "dwReserved1", "dwReserved2")]


JOY_RETURNBUTTONS = 0x80
JOY_RETURNPOV = 0x40
JOY_RETURNPOVCTS = 0x200
POV_CENTERED = 0xFFFF
POV_DIRECTIONS = {"up": 0, "right": 9000, "down": 18000, "left": 27000}


def key_name_to_vk(name):
    name = name.upper()
    if name in MOUSE_VK:
        return MOUSE_VK[name]
    if name not in FSO_SCANCODES:
        raise ValueError(f"unknown key '{name}'")
    sc = FSO_SCANCODES[name]
    if sc >= 0x80:
        sc = 0xE000 | (sc & 0x7F)
    vk = user32.MapVirtualKeyW(sc, MAPVK_VSC_TO_VK_EX)
    if not vk:
        raise ValueError(f"cannot map '{name}' to a virtual key")
    return vk


def vk_to_name(vk):
    if vk in VK_TO_MOUSE:
        return VK_TO_MOUSE[vk]
    sc = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
    if (sc & 0xFF00) in (0xE000, 0xE100) or vk in EXTENDED_VK:
        sc = (sc & 0x7F) | 0x80
    return SCANCODE_TO_NAME.get(sc)


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


PRETTY_KEYS = {"LCTRL": "Left Ctrl", "RCTRL": "Right Ctrl", "LSHIFT": "Left Shift",
               "RSHIFT": "Right Shift", "LALT": "Left Alt", "RALT": "Right Alt",
               "SPACEBAR": "Space", "CAPSLOCK": "Caps Lock", "ENTER": "Enter", "TAB": "Tab",
               "BACKSP": "Backspace", "ESC": "Esc"}


def key_label(name):
    """'KEY_RCTRL' -> 'Right Ctrl', 'KEY_PAD0' -> 'Numpad 0', 'MOUSE_X1' -> 'Mouse X1'."""
    if name.startswith("MOUSE_"):
        return "Mouse " + name[6:].capitalize() if len(name) > 8 else "Mouse " + name[6:]
    short = name[4:] if name.startswith("KEY_") else name
    if short in PRETTY_KEYS:
        return PRETTY_KEYS[short]
    if short.startswith("PAD"):
        return "Numpad " + short[3:].capitalize()
    return short.capitalize() if len(short) > 3 else short


class JOYCAPSW(ctypes.Structure):
    _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("szPname", wintypes.WCHAR * 32),
                ("rest", ctypes.c_byte * (728 - 4 - 64))]


def joystick_name(jid):
    """Product name of a controller ('T.16000M'), from the USB vendor/product id in the registry.

    winmm itself names every controller 'Microsoft PC-joystick driver'.
    """
    caps = JOYCAPSW()
    if winmm.joyGetDevCapsW(jid, ctypes.byref(caps), ctypes.sizeof(caps)) != 0:
        return f"Controller {jid + 1}"
    vidpid = f"VID_{caps.wMid:04X}&PID_{caps.wPid:04X}"
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, r"System\CurrentControlSet\Control\MediaProperties"
                                      r"\PrivateProperties\Joystick\OEM" + "\\" + vidpid) as k:
                name = str(winreg.QueryValueEx(k, "OEMName")[0]).strip()
                if name:
                    return name
        except OSError:
            pass
    return caps.szPname.strip() if "PC-joystick" not in caps.szPname else f"Controller {vidpid}"


def trigger_label(t):
    typ = t.get("type")
    if typ == "keyboard":
        return ("Mouse: " if t["key"].startswith("MOUSE_") else "Keyboard: ") + key_label(t["key"])
    pad = t.get("joy_name") or ("any controller" if int(t.get("joy_id", -1)) < 0
                                else f"Controller {int(t['joy_id']) + 1}")
    if typ == "joystick":
        return f"{pad}: button {int(t['button']) + 1}"
    if typ == "pov":
        return f"{pad}: hat {t.get('direction', 'up')}"
    return str(t)


class Joysticks:
    """Polls every connected winmm joystick (rescans periodically)."""

    def __init__(self):
        self.ids = []
        self.names = {}  # id -> product name
        self._last_scan = 0.0
        self.state = {}  # id -> (buttons_mask, pov)

    def ids_for(self, jid, name=None):
        """Controllers a trigger refers to: by name when known (ids change on reconnect), else id."""
        if name:
            match = [j for j in self.ids if self.names.get(j) == name]
            if match:
                return match
        return self.ids if jid < 0 else [jid]

    def _read(self, jid):
        info = JOYINFOEX()
        info.dwSize = ctypes.sizeof(JOYINFOEX)
        info.dwFlags = JOY_RETURNBUTTONS | JOY_RETURNPOV | JOY_RETURNPOVCTS
        if winmm.joyGetPosEx(jid, ctypes.byref(info)) == 0:
            return info.dwButtons, info.dwPOV
        return None

    def poll(self):
        now = time.monotonic()
        if now - self._last_scan > 5.0:
            self._last_scan = now
            self.ids = [j for j in range(winmm.joyGetNumDevs()) if self._read(j) is not None]
            self.names = {j: self.names.get(j) or joystick_name(j) for j in self.ids}
        state = {}
        for j in self.ids:
            r = self._read(j)
            if r is not None:
                state[j] = r
        self.state = state
        return state


def pov_matches(pov, direction):
    if pov == POV_CENTERED or pov > 36000:
        return False
    target = POV_DIRECTIONS[direction]
    diff = min(abs(pov - target), 36000 - abs(pov - target))
    return diff <= 4500  # include diagonals


class PushToTalk:
    """Background poller: is_pressed() is True while any enabled trigger is held."""

    def __init__(self, triggers, poll_hz=100):
        self.keys = []
        self.joy_buttons = []
        self.povs = []
        for t in triggers:
            if not t.get("enabled", True):
                continue
            typ = t.get("type")
            if typ == "keyboard":
                self.keys.append(key_name_to_vk(t["key"]))
            elif typ == "joystick":
                self.joy_buttons.append((int(t.get("joy_id", -1)), t.get("joy_name"), int(t["button"])))
            elif typ == "pov":
                d = t.get("direction", "up").lower()
                if d not in POV_DIRECTIONS:
                    raise ValueError(f"unknown POV direction '{d}'")
                self.povs.append((int(t.get("joy_id", -1)), t.get("joy_name"), d))
        self.joys = Joysticks() if (self.joy_buttons or self.povs) else None
        self._pressed = False
        self._interval = 1.0 / poll_hz
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @property
    def active(self):
        return bool(self.keys or self.joy_buttons or self.povs)

    def start(self):
        if self.active:
            self._thread.start()

    def stop(self):
        self._stop.set()

    def is_pressed(self):
        return self._pressed

    def _check(self):
        if any(key_down(vk) for vk in self.keys):
            return True
        if self.joys:
            state = self.joys.poll()
            for jid, name, btn in self.joy_buttons:
                for j in self.joys.ids_for(jid, name):
                    if j in state and state[j][0] & (1 << btn):
                        return True
            for jid, name, d in self.povs:
                for j in self.joys.ids_for(jid, name):
                    if j in state and pov_matches(state[j][1], d):
                        return True
        return False

    def _run(self):
        while not self._stop.is_set():
            self._pressed = self._check()
            time.sleep(self._interval)


class Capture:
    """Waits for the next new key, mouse button, controller button or hat press (GUI polling).

    poll() returns a trigger dict once something is pressed that wasn't held when the
    capture started, else None. The left mouse button is ignored (it clicks the GUI).
    """

    IGNORE_VK = GENERIC_VK | {0x01}

    def __init__(self):
        self.joys = Joysticks()
        self.prev_keys = self._keys()
        self.prev_joy = self.joys.poll()

    def _keys(self):
        return {vk for vk in range(1, 255) if vk not in self.IGNORE_VK and key_down(vk)}

    def poll(self):
        keys = self._keys()
        for vk in sorted(keys - self.prev_keys):
            name = vk_to_name(vk)
            if name:
                return {"type": "keyboard", "key": name}
        self.prev_keys = keys
        state = self.joys.poll()
        for j, (mask, pov) in state.items():
            pmask, ppov = self.prev_joy.get(j, (mask, pov))      # new device: baseline now
            new = mask & ~pmask
            name = self.joys.names.get(j)
            for b in range(32):
                if new & (1 << b):
                    return {"type": "joystick", "joy_id": j, "joy_name": name, "button": b}
            if pov != ppov and pov != POV_CENTERED and pov <= 36000:
                for d, target in POV_DIRECTIONS.items():
                    if pov == target:
                        return {"type": "pov", "joy_id": j, "joy_name": name, "direction": d}
        self.prev_joy = state
        return None


def learn(duration_s=None):
    """Print every key/button/POV pressed, to help configure triggers."""
    print("Press a key, a joystick/gamepad button or the POV hat (Ctrl+C to quit)...")
    joys = Joysticks()
    prev_keys = set()
    prev_joy = {}
    start = time.monotonic()
    while duration_s is None or time.monotonic() - start < duration_s:
        keys = {vk for vk in range(1, 255) if vk not in GENERIC_VK and key_down(vk)}
        for vk in keys - prev_keys:
            name = vk_to_name(vk)
            if name:
                print(f'  keyboard/mouse: {{"type": "keyboard", "key": "{name}"}}')
        prev_keys = keys
        state = joys.poll()
        for j, (mask, pov) in state.items():
            pmask, ppov = prev_joy.get(j, (0, POV_CENTERED))
            new = mask & ~pmask
            for b in range(32):
                if new & (1 << b):
                    print(f'  joystick {j}: {{"type": "joystick", "joy_id": {j}, "button": {b}}}')
            if pov != ppov and pov != POV_CENTERED and pov <= 36000:
                for d in POV_DIRECTIONS:
                    if pov == POV_DIRECTIONS[d]:
                        print(f'  joystick {j}: {{"type": "pov", "joy_id": {j}, "direction": "{d}"}}')
        prev_joy = state
        time.sleep(0.01)
