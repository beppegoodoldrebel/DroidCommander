"""Orders to wingmen through FreeSpace Open's comm menu.

FSO's wingman shortcuts ("attack my target", "cover me"...) don't send the order: they open
the comm menu "Give Command To" with that order already chosen. The game link script then
picks the recipient with the comm menu's Lua functions:
  - "Wingmen, cover me"     -> "All Fighters"
  - "Squad Alpha, cover me" -> "Wings", then Alpha, found by its name ("Alpha wing, cover me"
                               works too)
"""

# shortcuts that open the "Give Command To" menu (rearm goes straight to the support ship,
# capture skips to the ship list, so they are left alone)
SQUAD_SHORTCUTS = {"ATTACK_MESSAGE", "DISARM_MESSAGE", "DISABLE_MESSAGE", "ATTACK_SUBSYSTEM_MESSAGE",
                   "ENGAGE_MESSAGE", "FORM_MESSAGE", "IGNORE_MESSAGE", "PROTECT_MESSAGE",
                   "COVER_MESSAGE", "WARP_MESSAGE"}

WINGMEN = "Wingmen"          # the callsign whose orders go to all fighters
WING_PREFIX = "wing:"        # addressee of "Squad Alpha, ...": "wing:alpha"

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
