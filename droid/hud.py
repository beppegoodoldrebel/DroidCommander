"""What the droid writes among the game's HUD messages ("R2: Hull 72%, shields 45%").

Like the translation of an astromech's beeps on a cockpit screen. Shown only on your screen,
through the game link. How much it says is chosen in the Events tab ("game_link" -> "hud_messages"):
  off        nothing
  answers    answers to your questions, and why a command couldn't be done
  commands   also what each voice command did, and what it heard when it didn't understand
  everything also the game events the droid reacts to (hull low, subsystem lost, kills...)
"""

LEVELS = ["off", "answers", "commands", "everything"]
LEVEL_LABELS = {
    "off": "Off",
    "answers": "Answers and problems",
    "commands": "Also every command (recommended)",
    "everything": "Also game events",
}
DEFAULT_LEVEL = "commands"


def allowed(level, needed):
    """True if the chosen level includes messages of kind `needed`."""
    level = level if level in LEVELS else DEFAULT_LEVEL
    return LEVELS.index(level) >= LEVELS.index(needed) > 0


def sentence(text):
    text = str(text).strip()
    return text[:1].upper() + text[1:] if text else text


def event_text(event, detail):
    """HUD line for a game event the droid reacts to, or None (too frequent or obvious)."""
    if event == "kill":
        return "Target destroyed!"
    if event == "kill_capital":
        return "That's a big one down!"
    if event == "teamkill":
        return "That was a friendly!"
    if event == "ally_down":
        return "We lost a friendly ship."
    if event == "hull_low":
        return f"Hull down to {detail}%!" if detail else "Hull below 50%!"
    if event == "hull_critical":
        return f"Hull critical: {detail}%!" if detail else "Hull critical!"
    if event == "subsystem_lost":
        return f"We lost the {detail.lower()}!" if detail else "We lost a subsystem!"
    return None
