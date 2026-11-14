"""Orders to wingmen through FreeSpace Open's comm menu.

FSO's wingman shortcuts ("attack my target", "cover me"...) don't send the order: they open
the comm menu "Give Command To" with that order already chosen:

    1. Ships   2. Wings   3. All Ships   4. Reinforcements

So after the shortcut the droid also picks the recipient:
  - "Wingmen, cover me"     -> shortcut, then 3 (All Ships)
  - "Squad Alpha, cover me" -> shortcut, then 2 (Wings), then Alpha's number in that list
                               ("Alpha wing, cover me" works too).
The Wings list order comes from the game link (the Lua script writes it to droid_state.txt).
"""

from .phrases import normalize

# shortcuts that open the "Give Command To" menu (rearm goes straight to the support ship,
# capture skips to the ship list, so they are left alone)
SQUAD_SHORTCUTS = {"ATTACK_MESSAGE", "DISARM_MESSAGE", "DISABLE_MESSAGE", "ATTACK_SUBSYSTEM_MESSAGE",
                   "ENGAGE_MESSAGE", "FORM_MESSAGE", "IGNORE_MESSAGE", "PROTECT_MESSAGE",
                   "COVER_MESSAGE", "WARP_MESSAGE"}

WINGMEN = "Wingmen"          # the callsign whose orders go to all fighters
WING_PREFIX = "wing:"        # addressee of "Squad Alpha, ...": "wing:alpha"
MENU_WAIT_MS = 120           # let the menu open before choosing in it

# wing names you can say ("Squad Alpha, cover me"); edit them in the Droid tab
DEFAULT_WING_NAMES = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota",
                      "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau",
                      "phi", "chi", "psi", "omega", "red", "gold", "blue", "green",
                      "grey", "yellow", "silver", "cobalt", "rogue"]


def wing_label(group):
    """'wing:alpha' -> 'Alpha wing'."""
    return group[len(WING_PREFIX):].title() + " wing" if group and group.startswith(WING_PREFIX) else group


def is_squad_order(command):
    return any(a.get("bind") in SQUAD_SHORTCUTS for a in command.get("actions", []))


def find_wing(spoken, menu):
    """Position (1-based) of the spoken wing in the comm menu's Wings list, or None.

    'alpha' matches "Alpha"; it also matches "Alpha Aurek" if no other wing starts with Alpha.
    """
    spoken = normalize(spoken)
    names = [normalize(n) for n in menu]
    if spoken in names:
        return names.index(spoken) + 1
    starts = [i for i, n in enumerate(names) if n.split()[:len(spoken.split())] == spoken.split()]
    return starts[0] + 1 if len(starts) == 1 else None


def number_key(position):
    return "KEY_0" if position == 10 else f"KEY_{position}"


def recipient_actions(group, state):
    """Extra actions that pick who receives a wingman order. Raises ValueError with a reason."""
    if not group or not group.startswith(WING_PREFIX):
        return [{"wait": MENU_WAIT_MS}, {"key": "KEY_3"}]               # All Ships
    spoken = group[len(WING_PREFIX):]
    if state is None:
        raise ValueError("wing list unknown: install the game link (Events tab) and start a mission")
    menu = [n for n in str(state.get("wings") or "").split("|") if n]
    pos = find_wing(spoken, menu)
    if pos is None:
        same = [n for n in menu if normalize(n).split()[:len(spoken.split())] == spoken.split()]
        if len(same) > 1:
            raise ValueError(f"'{spoken.title()}' could be {', '.join(same)}: can't tell which")
        have = ", ".join(menu) or "none"
        raise ValueError(f"no wing '{spoken.title()}' to give orders to (wings: {have})")
    if pos > 10:
        raise ValueError(f"'{spoken.title()}' is beyond the first 10 wings of the comm menu")
    return [{"wait": MENU_WAIT_MS}, {"key": "KEY_2"}, {"wait": MENU_WAIT_MS}, {"key": number_key(pos)}]
