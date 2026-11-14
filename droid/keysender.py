"""Low level input injection via Win32 SendInput (scancodes, so SDL/FSO sees them)."""

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSE_FLAGS = {
    "LEFT_BUTTON": (0x0002, 0x0004),
    "RIGHT_BUTTON": (0x0008, 0x0010),
    "MIDDLE_BUTTON": (0x0020, 0x0040),
}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _send(inp):
    n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if n != 1:
        raise OSError(f"SendInput failed (error {ctypes.get_last_error()})")


def _key_event(scancode, up):
    flags = KEYEVENTF_SCANCODE
    if scancode >= 0x80:
        flags |= KEYEVENTF_EXTENDEDKEY
    if up:
        flags |= KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(0, scancode & 0x7F, flags, 0, 0)
    _send(inp)


def press_combo(combo, hold_ms=60):
    """Press modifiers + key, hold, then release in reverse order."""
    for m in combo.modifiers:
        _key_event(m, up=False)
    if combo.modifiers:
        time.sleep(0.015)
    _key_event(combo.scancode, up=False)
    time.sleep(hold_ms / 1000.0)
    _key_event(combo.scancode, up=True)
    for m in reversed(combo.modifiers):
        _key_event(m, up=True)


def click_mouse(button, hold_ms=60):
    down, up = MOUSE_FLAGS[button]
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(0, 0, 0, down, 0, 0)
    _send(inp)
    time.sleep(hold_ms / 1000.0)
    inp.mi = MOUSEINPUT(0, 0, 0, up, 0, 0)
    _send(inp)
