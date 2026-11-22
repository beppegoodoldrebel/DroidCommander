# Droid Commander

An astromech droid (R2, R5…) that listens to your voice commands, executes them in
FreeSpace Open / Fate of the Galaxy and answers with droid sounds.

> "R2, open S-foils" → the game link presses FotG's *Toggle S-foils* control inside the game → *beep-bweep!*

No key bindings are involved: commands name the game's controls (`CUSTOM_CONTROL_3`,
`MAX_THROTTLE`…) and a small Lua script inside FreeSpace Open (the **game link**) presses them,
whatever key, joystick button or nothing they are bound to, on any keyboard layout.

**Players:** download the installer from the [Releases](../../releases) page and read
[README_USERS.md](README_USERS.md) or the [user manual (PDF)](docs/DroidCommander_User_Manual.pdf).
This README is the technical documentation.

License: [MIT](LICENSE). An unofficial fan tool, not affiliated with Lucasfilm, Disney or the
Fate of the Galaxy team.

## Installing (for players)

Run **`DroidCommander-Setup-<version>.exe`**.

- No administrator rights are needed: it installs in `%LOCALAPPDATA%\Programs\Droid Commander`,
  with a Start menu shortcut and an optional desktop one.
- Everything is included (Python, the Vosk speech engine and the English speech model), so
  nothing else needs to be downloaded.
- Your settings, commands, voices and sound files live in `%APPDATA%\DroidCommander`. The
  uninstaller asks whether to keep them.
- At the first start, the app looks for FreeSpace Open (standard or Knossos.NET install) and
  opens the **Events** tab: press **Install game link** there. If Fate of the Galaxy isn't found
  (for example with a portable Knossos), press **Choose folder…** and pick the mod folder.
- Windows SmartScreen may warn about an "unknown publisher", because the program is not code
  signed: choose *More info → Run anyway*.

## Building the installer (for developers)

```bash
.venv\Scripts\pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

This needs [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the installer step. It produces:

- `dist\DroidCommander\`: the app, with `DroidCommander.exe` (the window) and
  `DroidCommanderEngine.exe` (the hidden listener started by LAUNCH!, plus the command-line
  tools);
- `dist\DroidCommander-Setup-<version>.exe`: the installer.

The version is in `droid/__init__.py`, and the defaults shipped to new users are in
`defaults/config/`. Third-party licenses are gathered into `packaging/licenses/` and installed
with the app.

## Installation (from source)

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python download_model.py
```

## Quick start

Double-click **`Droid Commander.bat`**. It is one window with two modes:

- **CONFIGURE**: the Droid, Commands and Voice tabs.
- **▶ LAUNCH!** (top right) switches the same window to **ACTIVE**: Droid Commander starts
  listening and the window shows:
  - a status lamp: starting / listening / push-to-talk;
  - the configuration in use: droid, callsigns, voice, listening modes, game link;
  - the last phrase heard, the last command with its result, and a log.

  **■ STOP · CONFIGURE** goes back to the tabs. Unsaved changes are offered for saving before
  launch.

The first time it goes ACTIVE, a bar asks whether to minimize the window to the taskbar (with an
option to remember the choice). The app reopens in the mode it was closed in, so if you quit
while it was listening, it starts listening right away next time.

`python -m droid app --active` / `--configure` force a mode. **`Droid Commander (console).bat`**
runs it without a GUI, in a console window.

## Droid name

The **Droid** tab of the editor sets the droid's name, e.g. "R2", "Chopper" or "BB-8".
Voice commands only run when they start with it ("Chopper, open S-foils").

- The name is turned into the forms the speech model may hear, which you can also edit by
  hand: letters can sound like words, so "R2" is also accepted as "are two", and "BB-8" as
  "bee bee eight".
- Words the model doesn't know are flagged.
- With push-to-talk the name is optional (see *Activation*).
- **Other callsigns**: besides the droid, you can give orders to other addressees. One per line,
  e.g. `Wingmen: wing men, wingman, squadron, flight`. In the Commands tab, a command's **To:**
  field says who it is addressed to, so "Wingmen, attack my target" goes to the wingmen while
  "R2, open S-foils" goes to the droid. Each addressee has its own phrases, so the same phrase
  can do different things for different addressees.
- A running Droid Commander switches to the new name as soon as you save.

### Orders to wingmen

FSO's wingman shortcuts (attack my target, cover me, form up…) don't send the order: they
open the comm menu **Give Command To** (Ships, Wings, All Fighters, Reinforcements) with the
order already chosen. The game link script presses the shortcut and then picks the recipient
with FSO's comm menu Lua functions (`hu.isCommMenuOpen()`, `mn.CommItems[i].Name` / `.Active` /
`:selectItem()`):

- **"Wingmen, cover me"**: "All Fighters".
- **"Squad Alpha, cover me"** (or "Alpha wing, cover me"): "Wings", then the wing **by its
  name**, so a wing that refuses an order can't shift the others. A bare name ("Alpha, …")
  isn't accepted, because short names like "nu" or "pi" would trigger by mistake. "Gold" also
  finds "Gold Aurek" when it's the only Gold wing.
- The names you can say are in the Droid tab → **Wing names** (Greek letters and colours by
  default; names the speech model doesn't know are ignored).
- A refused order closes the menu again and gives the error sound with the reason ("no wing
  omega (wings: Alpha, Gold Aurek…)", "which gold?", "Red can't take that order").
  The rearm and capture shortcuts don't use this menu and are left as they are.

## Game events (the droid reacts to the game)

The droid can react to what happens in FreeSpace Open: cheering when you destroy an enemy,
squealing when your hull is hit, alarm when the hull is low, and so on.

- **Events tab → Install game link** adds one small Lua script
  (`game_link/zz_droidcommander-sct.lua`) to the mod, in `data/tables/lua/`.
  - It hooks the game's events (`On Ship Death`, `On Pain Flash`, `On Simulation`,
    `On Ship Collision`, `On Subsystem Destroyed`, mission start/end) and appends them to
    `droid_link.log` in FreeSpace Open's user folder (`…/FreeSpaceOpen/<mod>/data/missions/`).
  - It runs every handler protected so it can't interrupt the game.
  - **Pressing controls from inside the game** (how every voice command reaches the game):
    the command is written to `droid_cmd.txt` (`seq|MAX_THROTTLE:1,WAIT:200,INCREASE_ENGINE:6`);
    the script reads it about 12 times per second, presses each control with FSO's Lua button
    controls (`ba.setButtonControlMode(BUTTON_CONTROL_LUA_ADDITIVE)`,
    `ControlInfo.useButtonControl`: held one frame, released one frame; by name, or by its fixed
    IoActionId number for the controls FSO's Lua name table lacks, such as `CUSTOM_CONTROL_1-5`)
    and answers in `droid_ack.txt`. No key bindings, keyboard layout or window focus are
    involved, and controls bound only to a joystick work. If no mission is running or the
    script doesn't answer within 0.6 s, the droid gives the error sound with the reason.
    Commands left in the file from before a mission starts are never run. The script reports
    its version in `droid_state.txt`, so the app warns when the game still runs an older copy
    (FSO loads scripts only at startup).
    **Commands → ▶ Test all in game…** (droid/test_all.py) tries every command at once during
    a mission: *Check names* sends `check:NAME,…` and the script answers which controls the
    game knows (nothing pressed); *Press all* presses each command one every 2 s (wingman
    orders optional, to all fighters; END_MISSION and WARP_MESSAGE are skipped).
    The Lua ADDITIVE button mode is on only while the script presses something: FSO copies
    the player's own buttons into the Lua buttons every frame in that mode, so leaving it on
    would make your own key presses repeat.
  - **Multiplayer:** it works there too, in fair-play mode: the droid only knows what your HUD shows:
    "are we clear?" counts only hostiles your radar can see (`checkVisibility`), not stealth
    ships or ships out of sensor range. Everything else it reports (hits, kills, hull,
    shields, energy, your target) is already on the HUD. Ask the server admins whether they
    allow it.
  - **Remove** deletes it. After a mod update, install it again (the tab shows the status).
  - **Mod folder:** found automatically in the Knossos library (the newest Fate of the Galaxy:
    `…/Library/FotG_R/FotG_R-1.1.3`, or for FotG 2, which is split into packages, its core
    package `…/Library/FotG_2/FotG_2-2.0.2/FG_Core`). If it isn't (another install location),
    press **Choose folder…** and pick the mod's version folder, its parent or a package
    folder. **Automatic** goes back to automatic detection.
  - Events are read from FreeSpace Open's user folder, also from FotG 2's package
    sub-folders (`…/FreeSpaceOpen/FotG_2-2.0.2/FG_Core/data/missions/`).
- Droid Commander reads that file about 10 times a second while ACTIVE. The ACTIVE view shows
  "Game link: connected" and logs every event.
- The **Reactions** table sets, for each event:
  - whether the droid reacts;
  - which response it plays: *Victory*, *Scared*, *Panic*, *Sad*, *Alarm*, *Greeting*, or any
    other;
  - a **chance** (%);
  - a **pause** (seconds before it reacts to the same event again).

  Answers to your voice commands always take priority over reactions.
- The new responses can be synthesized or use your own sound files, like the others
  (Voice tab).
- Note: Fate of the Galaxy's own in-cockpit droid also squeals when your hull is hit; lower or
  disable the *Your hull is hit* reaction if you get double squeals.

### Asking the droid

Once a second, the game link also writes a snapshot of your ship: hull, shields, weapon energy,
target, enemies left. Commands whose action is a **Question** make the droid answer with a
**Positive** or **Negative** sound, judged on that snapshot:

| Ask (e.g.) | Positive when | Notes |
|---|---|---|
| "R2, are you OK?" / "status report" | hull ≥ 60%, shields ≥ 30%, not hit in the last 8 s | panic below 25% hull |
| "R2, are we hit?" / "damage report" | hull ≥ 90% and not hit recently | |
| "R2, how are the shields?" | shields ≥ 50% | alarm below 20% |
| "R2, did we get him?" | you destroyed a ship in the last 12 s | victory sound |
| "R2, are we clear?" | no hostile ship left | |
| "R2, is the target damaged?" | target hull ≤ 50% | |
| "R2, do we have energy?" | weapon energy ≥ 50% | |

If you aren't flying (or the link isn't installed) the droid answers "not understood". The
Positive and Negative sounds can be synthesized or your own files (Voice tab). Add more phrasings
in the Commands tab, or new questions with **Add… → Question**.

## Game controls

Commands name FreeSpace Open's control actions (`droid/controls.py`: the IoActionId list, with
FSO's numbers). Their labels come from the mod's own `Controlconfigdefaults.tbl` (found in the
mod folder or a sibling package, e.g. FotG 2's `FG_Core`): FotG calls `CUSTOM_CONTROL_3`
"Toggle S-foils" and turned `TOGGLE_GLIDING` into "Toggle Active Pause". Key bindings don't
matter: the game link presses the control itself.

**⇩ Import from game…** lists every control, the mod's own ones first, with their labels. Tick
the ones you want and they become voice commands, named after the control and with phrases
made from the name ("Toggle S-foils" → "toggle s foils", "s foils"). Controls that already have
a command, or that the mod switches off, can't be ticked.

**When the mod changes its controls** (`droid/controls_watch.py`): at every start the editor
compares the mod's named controls with the ones it saw last time (`controls_seen` in
`settings.json`) and, if needed, opens **Game controls changed**:

- a **new** control (e.g. `CUSTOM_CONTROL_4` switched on as "Toggle Ion Cannon"): add a voice
  command for it, phrases included;
- a control a command uses that **now does something else** (its name changed completely, or
  — the first time — nothing in the command's name and phrases matches it, like "Toggle glide"
  on FotG 2's "Toggle Active Pause"): rename the command to match, switch it off, or keep it;
- a control the mod **switched off**: switch the command off.

*Ask me later* shows it again at the next start; *Ignore* remembers the current controls.

## Command editor

The **Commands** tab:

- add, duplicate, delete and enable/disable commands, with a search box;
- write phrases one per line. Words the speech model doesn't know and phrases used by two
  commands are flagged with ⚠;
- build the action list: **game controls** (picked from the list above, with a repeat count),
  **waits** and **questions**;
- choose the response sound and play it;
- **Test in game**: runs the command after a 5-second countdown (time to click into the game:
  FSO pauses when it isn't in front);
- **▶ Test all in game…** (`droid/test_all.py`): *Check names* asks the game which controls it
  knows (nothing pressed); *Press all* presses each command one every 2 s (wingman orders
  optional, to all fighters; END_MISSION, WARP_MESSAGE and TOGGLE_GLIDING are skipped);
- **Try a phrase**: type what you would say and see which command it triggers.

Saving keeps a `commands.json.bak` backup of the previous file, and a running Droid
Commander reloads the commands within a couple of seconds. You don't need to restart it,
even mid-game. Old commands with keyboard keys or mouse buttons are flagged ⚠: replace those
actions with game controls.

## Droid voice

The droid's answers are synthesized live, so it never sounds exactly the same twice. The
**Voice** tab of the editor shapes how it talks:

- **Presets:** *R2-D2 style* (expressive whistles), *R5 style* (lower, with a
  faulty-motivator stutter), *Chopper style* (grumpy, gritty, grinding gears),
  *BB-8 style* (soft, round, quick coos) and *Songbird* (pure, bird-like trills).
- **Vocal tone** slider: blends from the bird-like whistle (0) to a human-like "uoooo" vowel (1).
  The vowel is made source-filter style: a harmonic voice source through three parallel formant
  resonances that glide u → o → open o as the note gets louder. It adds an unsteady pitch, a
  scoop on attacks, and a little breath and growl from Grit. *Chopper style* is built on it.
- **22 sliders** in three groups:
  - pitch and tempo: pitch, range, speed, syllable and gap length, talkativeness;
  - melody and mood: glide, steady beeps, vibrato, trills, attitude from grumpy to cheerful;
  - timbre: overtones, metallic shimmer, grit, mechanical noise, metal body, softness,
    brightness, room, glitches.

The engine is modelled on bird song: an almost pure whistle with fluid pitch
movements and bell-shaped envelopes. Overtones are band-limited, everything goes through
a low-pass filter, and loudness is normalised, so no combination of sliders becomes shrill
or clicky.
- **Listen** buttons for each mood (acknowledged, error, not understood, ready, chatter).
  Every slider can also play automatically when you release it.
- **🎲 Surprise me** makes a random variation of the current voice.
- **Save as…** keeps your own voices in `config/voices.json`. The chosen voice is used
  right away by a running Droid Commander.

The R2-D2 preset was tuned by measuring general characteristics of reference astromech
sounds: syllable length, pitch range, glide speed, vibrato rate and depth. No audio was
copied.

**Sound-file voices:** set a voice's **Source** to *Sound files* to use your own recordings
instead of the synthesizer.
- For each response (Acknowledged, Error, Not understood, Ready, Chatter), add one or more
  files (WAV, OGG, FLAC, MP3). The droid plays one of them at random.
- Saving copies the files into `sounds/voices/<voice>/<response>/`, so the voice is a
  self-contained preset.
- A response with no files falls back to the synthesized voice.

In the Commands tab, a command only picks which **response** the droid gives; the sound
itself comes from the active voice.

## Audio setup (Setup tab)

Useful when the PC has several sound cards, headsets or virtual audio drivers.

- **Microphone:** the input the droid listens to. *Windows default* follows Windows'
  setting. **🎙 Test microphone** shows a live level bar: speak and it should move.
- **Droid audio output:** where the droid's voice plays. *Windows default* (recommended)
  uses Windows' own sound system and works on every PC. A specific device (for example
  speakers while the game uses your headset) uses PortAudio; press **▶ Test**, and if it is
  silent go back to Windows default.
- **Master volume:** the loudness of every droid sound, synthesized voices and sound files
  alike. It is saved in `config/voices.json` immediately and also applies to a running
  Droid Commander. If it isn't set there, `sound.volume` in `settings.json` is used.

Microphone and output are saved by **Save** in `settings.json` (`microphone`, `sound.backend`,
`sound.output_device`, stored by device name because indices change) and are used from the
next LAUNCH!.

## Usage

| Command | What it does |
|---|---|
| `python -m droid` | start listening |
| `python -m droid check` | validate commands and the speech model vocabulary |
| `python -m droid binds` | show the game control each command presses, with the mod's name for it |
| `python -m droid test "open s foils"` | run a command without voice, during a mission (5 s to switch to the game) |
| `python -m droid learn` | print the names of pressed keys/buttons, to configure push-to-talk |
| `python -m droid sound ack` | play a sound (`ack`, `error`, `unknown`, `ready`, `chatter`) |
| `python -m droid mics` | list microphones (or pick one in the Setup tab) |
| `python -m droid speakers` | play a chirp on every output device; put the one you hear in `settings.json` → `sound` → `output_device` (index or part of the name, only used with `"backend": "sounddevice"`) |

**Audio backend:** by default sounds are played by Windows itself (`"backend": "winsound"`),
on the default output device. On some systems the PortAudio library is silent with no error;
if you need to pick a specific output device, set `"backend": "sounddevice"`.

`-v` also shows what the recognizer is hearing.

## Activation

Choose one mode in the **Setup tab → Talking to the droid**:

- **Always listening** (default): commands start with the droid's name (see *Droid name*).
- **Push-to-talk**: the droid listens only while you hold a key or button. Press **＋ Add key or button**
  and then the key: keyboard keys, mouse middle/side buttons, and buttons or hats of any
  joystick, throttle or gamepad (each controller is remembered by its product name, e.g.
  "T.Flight Hotas X: button 4", so it keeps working if Windows renumbers controllers).
  Holding a listed key in the Setup tab lights up its line, as a quick test. The droid name
  is optional while holding it, unless *Require the name* is ticked.
  Pick a key or button that is **not** bound in the game.

They are stored in `settings.json` → `activation`; `python -m droid learn` prints every
key and button pressed, if you prefer editing the file.

## Commands (`config/commands.json`)

```json
{
  "name": "Toggle S-foils",
  "phrases": ["open s foils", "close s foils"],
  "actions": [{ "bind": "CUSTOM_CONTROL_3" }],
  "sound": "ack"
}
```

Available actions (they can be chained):

- `{"bind": "INCREASE_ENGINE", "repeat": 6}`: a game control (FSO's name), pressed inside the
  game by the game link, whatever it is bound to.
- `{"wait": 200}`: pause in milliseconds (mission time: it stops while the game is paused).
- `{"ask": "clear"}`: a question the droid answers from your ship's state.

Old `{"key": …}` and `{"mouse": …}` actions are no longer supported (flagged ⚠ in the editor).

Write phrases naturally: "R2" becomes "r two" and "S-foil" becomes "s foil".

**Vocabulary:** the speech model only knows certain words. For example "wingmen" is not
there, so write "wing men". `python -m droid check` lists unknown words and the commands
that use them.

**Tolerant matching:** Vosk sometimes adds stray words ("full power *will* to engines").
So commands are also matched by similarity (`fuzzy_match` in `settings.json`, 0 to 1;
higher = stricter). If a phrase is ambiguous between two commands, the droid answers
"not understood". The droid name also has phonetic variants ("are two"), because "R2" is
often heard that way.

## Known limitations

- Voice commands need the game link and a mission running: outside a mission the droid
  answers with the error sound.
- S-foils are a *toggle*: "open" and "close" press the same control.
- FSO loads the game link only when it starts: after installing or updating it, restart the
  game (the Events tab warns when the game still runs an older copy).
