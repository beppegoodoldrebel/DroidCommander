"""FreeSpace Open key names -> DirectInput-style scancodes.

FSO stores keys with the same numbering as DirectInput (DIK_*): values >= 0x80
are "extended" keys, sent to Windows as (code & 0x7F) + KEYEVENTF_EXTENDEDKEY.
Scancodes are position based, so they work regardless of keyboard layout
(e.g. KEY_SEMICOL is the 'ò' key on an Italian keyboard).
"""

FSO_SCANCODES = {
    "KEY_ESC": 0x01,
    "KEY_1": 0x02, "KEY_2": 0x03, "KEY_3": 0x04, "KEY_4": 0x05, "KEY_5": 0x06,
    "KEY_6": 0x07, "KEY_7": 0x08, "KEY_8": 0x09, "KEY_9": 0x0A, "KEY_0": 0x0B,
    "KEY_MINUS": 0x0C, "KEY_EQUAL": 0x0D, "KEY_BACKSP": 0x0E, "KEY_TAB": 0x0F,
    "KEY_Q": 0x10, "KEY_W": 0x11, "KEY_E": 0x12, "KEY_R": 0x13, "KEY_T": 0x14,
    "KEY_Y": 0x15, "KEY_U": 0x16, "KEY_I": 0x17, "KEY_O": 0x18, "KEY_P": 0x19,
    "KEY_LBRACKET": 0x1A, "KEY_RBRACKET": 0x1B, "KEY_ENTER": 0x1C, "KEY_LCTRL": 0x1D,
    "KEY_A": 0x1E, "KEY_S": 0x1F, "KEY_D": 0x20, "KEY_F": 0x21, "KEY_G": 0x22,
    "KEY_H": 0x23, "KEY_J": 0x24, "KEY_K": 0x25, "KEY_L": 0x26,
    "KEY_SEMICOL": 0x27, "KEY_RAPOSTRO": 0x28, "KEY_LAPOSTRO": 0x29,
    # careful, FSO's names (code/io/key.h): KEY_SLASH is the '\' key, KEY_DIVIDE the '/' key
    "KEY_LSHIFT": 0x2A, "KEY_SLASH": 0x2B,
    "KEY_Z": 0x2C, "KEY_X": 0x2D, "KEY_C": 0x2E, "KEY_V": 0x2F, "KEY_B": 0x30,
    "KEY_N": 0x31, "KEY_M": 0x32,
    "KEY_COMMA": 0x33, "KEY_PERIOD": 0x34, "KEY_DIVIDE": 0x35, "KEY_RSHIFT": 0x36,
    "KEY_PADMULTIPLY": 0x37, "KEY_LALT": 0x38, "KEY_SPACEBAR": 0x39, "KEY_CAPSLOCK": 0x3A,
    "KEY_F1": 0x3B, "KEY_F2": 0x3C, "KEY_F3": 0x3D, "KEY_F4": 0x3E, "KEY_F5": 0x3F,
    "KEY_F6": 0x40, "KEY_F7": 0x41, "KEY_F8": 0x42, "KEY_F9": 0x43, "KEY_F10": 0x44,
    "KEY_NUMLOCK": 0x45, "KEY_SCROLLOCK": 0x46,
    "KEY_PAD7": 0x47, "KEY_PAD8": 0x48, "KEY_PAD9": 0x49, "KEY_PADMINUS": 0x4A,
    "KEY_PAD4": 0x4B, "KEY_PAD5": 0x4C, "KEY_PAD6": 0x4D, "KEY_PADPLUS": 0x4E,
    "KEY_PAD1": 0x4F, "KEY_PAD2": 0x50, "KEY_PAD3": 0x51, "KEY_PAD0": 0x52,
    "KEY_PADPERIOD": 0x53, "KEY_SLASH_UK": 0x56, "KEY_F11": 0x57, "KEY_F12": 0x58,
    # extended keys
    "KEY_PADENTER": 0x9C, "KEY_RCTRL": 0x9D, "KEY_PADDIVIDE": 0xB5,
    "KEY_PRINT_SCRN": 0xB7, "KEY_RALT": 0xB8, "KEY_BREAK": 0xC6,
    "KEY_HOME": 0xC7, "KEY_UP": 0xC8, "KEY_PAGEUP": 0xC9, "KEY_LEFT": 0xCB,
    "KEY_RIGHT": 0xCD, "KEY_END": 0xCF, "KEY_DOWN": 0xD0, "KEY_PAGEDOWN": 0xD1,
    "KEY_INSERT": 0xD2, "KEY_DELETE": 0xD3,
}

SCANCODE_TO_NAME = {v: k for k, v in FSO_SCANCODES.items()}

MODIFIER_SCANCODES = {
    "SHIFT": FSO_SCANCODES["KEY_LSHIFT"],
    "ALT": FSO_SCANCODES["KEY_LALT"],
    "CTRL": FSO_SCANCODES["KEY_LCTRL"],
}

MOUSE_BUTTONS = ("LEFT_BUTTON", "RIGHT_BUTTON", "MIDDLE_BUTTON")


class KeyCombo:
    def __init__(self, text, modifiers, scancode):
        self.text = text
        self.modifiers = modifiers   # list of scancodes
        self.scancode = scancode

    def __repr__(self):
        return f"KeyCombo({self.text})"


def parse_key(text):
    """Parse an FSO key string like 'ALT-SHIFT-KEY_T' into a KeyCombo.

    Raises ValueError for unknown names.
    """
    text = text.strip().upper()
    parts = text.split("-")
    key = parts[-1]
    mods = []
    for m in parts[:-1]:
        if m not in MODIFIER_SCANCODES:
            raise ValueError(f"unknown modifier '{m}' in '{text}'")
        mods.append(MODIFIER_SCANCODES[m])
    if key not in FSO_SCANCODES:
        raise ValueError(f"unknown key '{key}' in '{text}'")
    return KeyCombo(text, mods, FSO_SCANCODES[key])
