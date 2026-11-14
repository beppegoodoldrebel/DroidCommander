# Droid Commander — README for players

**Talk to your astromech droid in Fate of the Galaxy.** Say "R2, open S-foils" and the droid
presses the right key for you, then answers with droid beeps. It also reacts to what happens
in the game (a kill, a hit, low hull…), answers simple questions ("R2, are we clear?") and
relays your orders to your wingmen ("Squad Alpha, cover me").

The full user manual with pictures is **DroidCommander_User_Manual.pdf**, in the program
folder and in the Start menu (*Droid Commander User Manual*).

---

## What you need

- Windows 10 or 11
- **Fate of the Galaxy** installed with Knossos.NET (FotG 1 or FotG 2)
- A microphone (a headset works best)
- English voice commands (the speech recognition works offline, nothing is sent to the internet)

## Install

1. Run **DroidCommander-Setup-1.0.0.exe** and follow the steps. No administrator rights needed.
2. Start **Droid Commander** from the Start menu (or the desktop icon).

Everything is included: the speech model, the droid voices and the game link script.
Your settings are kept in `%APPDATA%\DroidCommander` and survive updates.

## First start in 5 steps

1. **Commands tab → Game controls → Browse…** and choose FreeSpace Open's `data\players`
   folder, e.g. `…\kn_portable\HardLightProductions\FreeSpaceOpen\data\players`.
   Choose **Follow pilot** and your pilot: the droid then always uses the keys of that pilot.
2. **Setup tab:** pick your **microphone** and press **Test microphone** — the bar must move
   when you speak. Leave the audio output on *Windows default* unless you need something else.
3. **Events tab → Install game link** (restart the game if it is running). This lets the droid
   react to the game and answer questions.
4. Press **LAUNCH!**. The window switches to the active view and shows *LISTENING*.
5. Start a mission and say: **"R2, full throttle"**.

## How to talk to the droid

Start every command with the droid's name, then the order:

| You say | What happens |
|---|---|
| "R2, open S-foils" | toggles the S-foils |
| "R2, target nearest enemy" | targets the closest hostile |
| "R2, full power to engines" | moves all power to engines |
| "R2, shields front" | doubles the front shields |
| "R2, are we clear?" | the droid answers: happy beep = yes, sad beep = no |
| "Wingmen, attack my target" | order to **all** your wingmen |
| "Squad Alpha, cover me" | order to **Alpha wing** only |

The full list of commands is in the **Commands** tab: every one can be changed, disabled,
or created from scratch (**Import from game…** adds commands for any game control).

**Push-to-talk:** in the Setup tab you can switch from *Always listening* to *Push-to-talk*:
the droid then listens only while you hold a key, a mouse button or any joystick / throttle /
gamepad button. Pick one that is not used in the game.

## The tabs in short

- **Droid** — the droid's name (wake word), other callsigns (Wingmen) and wing names.
- **Commands** — what you can say and which key each command presses.
- **Voice** — how the droid sounds: R2-D2, R5, Chopper, BB-8 or Songbird style, your own
  variations, or your own sound files.
- **Events** — install the game link and choose how the droid reacts to game events.
- **Setup** — microphone, push-to-talk, audio output and master volume.

## Troubleshooting

| Problem | Try this |
|---|---|
| The droid hears nothing | Setup tab → Test microphone. Pick the right microphone; speak a bit closer. |
| It hears me but nothing happens | Commands tab: a ⚠ next to a command means its key isn't found in your game preset (often bound only to a joystick). Add a keyboard key in the game's controls. |
| "The game is not in the foreground" | Click into the game window. If the game runs as administrator, run Droid Commander as administrator too. |
| I can't hear the droid | Setup tab → output *Windows default* → Test. Check the master volume. |
| The droid doesn't react to the game | Events tab: install (or **Update**) the game link, restart the game, start a mission. If FotG isn't found, press **Choose folder…** and pick the mod folder. |
| "Squad Alpha" gives an error beep | That wing isn't in the mission (or has no ships left), or the game link isn't installed. |
| Wrong command recognized | Speak the phrase as written in the Commands tab; add your own wording as an extra phrase. |

## Multiplayer

The game link also works in multiplayer, in **fair-play mode**: the droid only knows what
your HUD shows (for example "are we clear?" counts only enemies on your radar). Ask your
server admins whether they allow it.

## Uninstall

Windows Settings → Apps → **Droid Commander** → Uninstall. To remove the game link from the
mod first, use **Events tab → Remove**. Your settings stay in `%APPDATA%\DroidCommander`;
delete that folder to remove them too.

---

*Droid Commander is a fan project, not affiliated with Lucasfilm, Disney or the Fate of the
Galaxy team. Speech recognition: Vosk (offline).*
