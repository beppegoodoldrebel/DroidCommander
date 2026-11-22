"""The game's controls: every FreeSpace Open control action, with the names the mod gives them.

Voice commands press controls by name (MAX_THROTTLE, CUSTOM_CONTROL_3…) through the game link,
so no keyboard layout or key binding is involved. The list and the numbers are FSO's
IoActionId (code/controlconfig/controlsconfig.h); the labels a mod shows in its control
options ("Toggle S-foils") come from its Controlconfigdefaults.tbl.
"""

import glob
import os
import re

# name -> number (IoActionId). Axes, comm menu navigation and photo mode aren't voice commands.
CONTROLS = {
    "TARGET_NEXT": 0, "TARGET_PREV": 1, "TARGET_NEXT_CLOSEST_HOSTILE": 2,
    "TARGET_PREV_CLOSEST_HOSTILE": 3, "TOGGLE_AUTO_TARGETING": 4, "TARGET_NEXT_CLOSEST_FRIENDLY": 5,
    "TARGET_PREV_CLOSEST_FRIENDLY": 6, "TARGET_SHIP_IN_RETICLE": 7,
    "TARGET_CLOSEST_SHIP_ATTACKING_TARGET": 8, "TARGET_LAST_TRANMISSION_SENDER": 9,
    "STOP_TARGETING_SHIP": 10, "TARGET_SUBOBJECT_IN_RETICLE": 11, "TARGET_NEXT_SUBOBJECT": 12,
    "TARGET_PREV_SUBOBJECT": 13, "STOP_TARGETING_SUBSYSTEM": 14, "MATCH_TARGET_SPEED": 15,
    "TOGGLE_AUTO_MATCH_TARGET_SPEED": 16, "FIRE_PRIMARY": 17, "FIRE_SECONDARY": 18,
    "CYCLE_NEXT_PRIMARY": 19, "CYCLE_PREV_PRIMARY": 20, "CYCLE_SECONDARY": 21, "CYCLE_NUM_MISSLES": 22,
    "LAUNCH_COUNTERMEASURE": 23, "FORWARD_THRUST": 24, "REVERSE_THRUST": 25, "BANK_LEFT": 26,
    "BANK_RIGHT": 27, "PITCH_FORWARD": 28, "PITCH_BACK": 29, "YAW_LEFT": 30, "YAW_RIGHT": 31,
    "ZERO_THROTTLE": 32, "MAX_THROTTLE": 33, "ONE_THIRD_THROTTLE": 34, "TWO_THIRDS_THROTTLE": 35,
    "PLUS_5_PERCENT_THROTTLE": 36, "MINUS_5_PERCENT_THROTTLE": 37, "ATTACK_MESSAGE": 38,
    "DISARM_MESSAGE": 39, "DISABLE_MESSAGE": 40, "ATTACK_SUBSYSTEM_MESSAGE": 41, "CAPTURE_MESSAGE": 42,
    "ENGAGE_MESSAGE": 43, "FORM_MESSAGE": 44, "IGNORE_MESSAGE": 45, "PROTECT_MESSAGE": 46,
    "COVER_MESSAGE": 47, "WARP_MESSAGE": 48, "REARM_MESSAGE": 49, "TARGET_CLOSEST_SHIP_ATTACKING_SELF": 50,
    "VIEW_CHASE": 51, "VIEW_EXTERNAL": 52, "VIEW_EXTERNAL_TOGGLE_CAMERA_LOCK": 53, "VIEW_SLEW": 54,
    "VIEW_OTHER_SHIP": 55, "VIEW_DIST_INCREASE": 56, "VIEW_DIST_DECREASE": 57, "VIEW_CENTER": 58,
    "PADLOCK_UP": 59, "PADLOCK_DOWN": 60, "PADLOCK_LEFT": 61, "PADLOCK_RIGHT": 62,
    "RADAR_RANGE_CYCLE": 63, "SQUADMSG_MENU": 64, "SHOW_GOALS": 65, "END_MISSION": 66,
    "TARGET_TARGETS_TARGET": 67, "AFTERBURNER": 68, "INCREASE_WEAPON": 69, "DECREASE_WEAPON": 70,
    "INCREASE_SHIELD": 71, "DECREASE_SHIELD": 72, "INCREASE_ENGINE": 73, "DECREASE_ENGINE": 74,
    "ETS_EQUALIZE": 75, "SHIELD_EQUALIZE": 76, "SHIELD_XFER_TOP": 77, "SHIELD_XFER_BOTTOM": 78,
    "SHIELD_XFER_LEFT": 79, "SHIELD_XFER_RIGHT": 80, "XFER_SHIELD": 81, "XFER_LASER": 82,
    "GLIDE_WHEN_PRESSED": 83, "BANK_WHEN_PRESSED": 84, "SHOW_NAVMAP": 85, "ADD_REMOVE_ESCORT": 86,
    "ESCORT_CLEAR": 87, "TARGET_NEXT_ESCORT_SHIP": 88, "TARGET_CLOSEST_REPAIR_SHIP": 89,
    "TARGET_NEXT_UNINSPECTED_CARGO": 90, "TARGET_PREV_UNINSPECTED_CARGO": 91, "TARGET_NEWEST_SHIP": 92,
    "TARGET_NEXT_LIVE_TURRET": 93, "TARGET_PREV_LIVE_TURRET": 94, "TARGET_NEXT_BOMB": 95,
    "TARGET_PREV_BOMB": 96, "MULTI_MESSAGE_ALL": 97, "MULTI_MESSAGE_FRIENDLY": 98,
    "MULTI_MESSAGE_HOSTILE": 99, "MULTI_MESSAGE_TARGET": 100, "MULTI_OBSERVER_ZOOM_TO": 101,
    "TIME_SPEED_UP": 102, "TIME_SLOW_DOWN": 103, "TOGGLE_HUD_CONTRAST": 104, "MULTI_TOGGLE_NETINFO": 105,
    "MULTI_SELF_DESTRUCT": 106, "TOGGLE_HUD": 107, "RIGHT_SLIDE_THRUST": 108, "LEFT_SLIDE_THRUST": 109,
    "UP_SLIDE_THRUST": 110, "DOWN_SLIDE_THRUST": 111, "HUD_TARGETBOX_TOGGLE_WIREFRAME": 112,
    "VIEW_TOPDOWN": 113, "VIEW_TRACK_TARGET": 114, "AUTO_PILOT_TOGGLE": 115, "NAV_CYCLE": 116,
    "TOGGLE_GLIDING": 117, "CYCLE_PRIMARY_WEAPON_SEQUENCE": 118, "CUSTOM_CONTROL_1": 119,
    "CUSTOM_CONTROL_2": 120, "CUSTOM_CONTROL_3": 121, "CUSTOM_CONTROL_4": 122, "CUSTOM_CONTROL_5": 123,
    "TOGGLE_HUD_SHADOWS": 132, "CYCLE_PRIMARY_WEAPON_PATTERN": 133,
}

# FreeSpace Open's own labels where the name alone reads badly
STANDARD_LABELS = {
    "TARGET_NEXT_CLOSEST_HOSTILE": "Target Next Closest Hostile Ship",
    "TARGET_CLOSEST_SHIP_ATTACKING_SELF": "Target Closest Attacking Ship",
    "TARGET_LAST_TRANMISSION_SENDER": "Target Last Transmission Sender",
    "CYCLE_NUM_MISSLES": "Cycle Secondary Weapon Firing Rate", "XFER_SHIELD": "Transfer Energy Laser->Shield",
    "XFER_LASER": "Transfer Energy Shield->Laser", "ETS_EQUALIZE": "Equalize Energy Settings",
    "SHIELD_XFER_TOP": "Augment Forward Shield", "SHIELD_XFER_BOTTOM": "Augment Rear Shield",
    "SHIELD_XFER_LEFT": "Augment Left Shield", "SHIELD_XFER_RIGHT": "Augment Right Shield",
    "SQUADMSG_MENU": "Communications Menu", "END_MISSION": "Warp Out", "TOGGLE_GLIDING": "Toggle Gliding",
    "TARGET_TARGETS_TARGET": "Target Target's Target", "ATTACK_MESSAGE": "Wingmen: Attack My Target",
    "DISARM_MESSAGE": "Wingmen: Disarm My Target", "DISABLE_MESSAGE": "Wingmen: Disable My Target",
    "ATTACK_SUBSYSTEM_MESSAGE": "Wingmen: Destroy My Subsystem", "CAPTURE_MESSAGE": "Wingmen: Capture My Target",
    "ENGAGE_MESSAGE": "Wingmen: Engage Enemy", "FORM_MESSAGE": "Wingmen: Form On My Wing",
    "IGNORE_MESSAGE": "Wingmen: Ignore My Target", "PROTECT_MESSAGE": "Wingmen: Protect My Target",
    "COVER_MESSAGE": "Wingmen: Cover Me", "WARP_MESSAGE": "Wingmen: Return To Base",
    "REARM_MESSAGE": "Rearm Me",
}

TABLE = "Controlconfigdefaults.tbl"


def standard_label(name):
    """FSO's own description of a control: 'MAX_THROTTLE' -> 'Max Throttle'."""
    if name in STANDARD_LABELS:
        return STANDARD_LABELS[name]
    return name.replace("_", " ").title().replace("Hud", "HUD").replace("Ets", "ETS")


def find_table(mod_dir):
    """The mod's control table: in its own data/tables, or in a sibling package (FotG 2)."""
    if not mod_dir:
        return None
    candidates = [os.path.join(mod_dir, "data", "tables", TABLE)]
    candidates += glob.glob(os.path.join(os.path.dirname(mod_dir), "*", "data", "tables", TABLE))
    return next((c for c in candidates if os.path.exists(c)), None)


def load_mod_controls(mod_dir):
    """{name: {"label": str or None, "disabled": bool}} from the mod's Controlconfigdefaults.tbl."""
    path = find_table(mod_dir)
    out = {}
    if not path:
        return out
    current = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.split(";", 1)[0] if not line.lstrip().startswith("$Has XStr") else line
            m = re.match(r"\s*\$Bind:\s*(\w+)", line)
            if m:
                current = m.group(1)
                out.setdefault(current, {"label": None, "disabled": False})
                continue
            if current is None:
                continue
            m = re.match(r'\s*\$Has XStr:.*?;\s*"([^"]+)"', line)
            if m:
                out[current]["label"] = m.group(1)
                continue
            m = re.match(r"\s*\$Disable:\s*(\w+)", line)
            if m:
                out[current]["disabled"] = m.group(1).lower() in ("true", "yes", "1")
    return out


class Catalog:
    """The controls of the installed game: FSO's list with the mod's names on top."""

    def __init__(self, mod_dir=None):
        self.mod_dir = mod_dir
        self.mod = load_mod_controls(mod_dir)

    def known(self, name):
        return name in CONTROLS

    def label(self, name):
        info = self.mod.get(name) or {}
        return info.get("label") or standard_label(name)

    def from_mod(self, name):
        """True if the mod gives this control its own name (e.g. FotG's 'Toggle S-foils')."""
        return bool((self.mod.get(name) or {}).get("label"))

    def disabled(self, name):
        return bool((self.mod.get(name) or {}).get("disabled"))

    def names(self):
        return list(CONTROLS)

    def snapshot(self):
        """What to remember, to notice changes after a mod update: {name: label} of named controls."""
        return {n: i["label"] for n, i in self.mod.items() if i.get("label") and not i.get("disabled")}
