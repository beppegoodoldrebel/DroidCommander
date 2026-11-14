"""Parametric astromech voice synthesizer, bird-song style.

A droid "utterance" is a few syllables separated by short gaps. Each syllable is a
whistle with a pitch contour (steady beep, glide, or arch) plus optional slow vibrato or
a fast trill. Like bird song, the core tone is an almost pure sine with fluid frequency
modulation and smooth, bell-shaped amplitude envelopes. Colour is added gently on top:
band-limited overtones, a soft metallic shimmer, light saturation, mechanical noise and
a tin-can body resonance. Then the whole utterance goes through a low-pass "brightness"
filter, an optional small room reverb, and loudness normalisation, so no setting ends up
shrill or clicky.

A *voice* is a dict of parameters (see PARAMS), so very different droids come from the
same engine. The R2 defaults were tuned by measuring general statistics of reference
astromech sounds (syllable length, pitch range, glide speed, vibrato), not by copying
any of them.
"""

import numpy as np

SR = 44100
TARGET_RMS = 0.13      # loudness of the voiced parts after normalisation
PEAK_LIMIT = 0.75

# key, label, min, max, resolution, description
PARAMS = [
    ("pitch", "Pitch (Hz)", 100, 2500, 10, "Centre pitch of the voice"),
    ("range", "Pitch range (octaves)", 0.2, 3.0, 0.05, "How far syllables wander from the centre"),
    ("speed", "Speed", 0.5, 2.0, 0.05, "Overall tempo: higher = faster droid"),
    ("syllable_ms", "Syllable length (ms)", 40, 600, 5, "Typical length of one beep/whistle"),
    ("gap_ms", "Gap length (ms)", 10, 400, 5, "Silence between syllables"),
    ("talk", "Talkativeness", 0.5, 2.0, 0.05, "Number of syllables per answer"),
    ("glide", "Glide (octaves/s)", 0.0, 15.0, 0.1, "Speed of pitch sweeps"),
    ("steady", "Steady beeps", 0.0, 1.0, 0.01, "Share of flat, constant-pitch beeps"),
    ("vib_rate", "Vibrato rate (Hz)", 2.0, 25.0, 0.1, "Speed of the slow warble"),
    ("vib_depth", "Vibrato depth (cents)", 0, 1500, 10, "Width of the warble (100 cents = 1 semitone)"),
    ("vib_share", "Vibrato amount", 0.0, 1.0, 0.01, "Share of syllables with vibrato"),
    ("trill", "Trills", 0.0, 1.0, 0.01, "Share of syllables with a fast, bird-like trill"),
    ("attitude", "Attitude", -1.0, 1.0, 0.05, "-1 grumpy (falling) ... +1 cheerful (rising)"),
    ("brass", "Vocal tone", 0.0, 1.0, 0.01, "0 = bird-like whistle, 1 = human-like \"uoooo\" vowel"),
    ("harmonics", "Overtones", 0.0, 1.0, 0.01, "0 = pure whistle, 1 = fuller, reedy tone"),
    ("ring", "Metallic shimmer", 0.0, 1.0, 0.01, "Bell-like, robotic colour"),
    ("grit", "Grit", 0.0, 1.0, 0.01, "Roughness: grumpy, buzzy edge"),
    ("noise", "Mechanical noise", 0.0, 1.0, 0.01, "Gear grinding and servo whirs"),
    ("body", "Metal body", 0.0, 1.0, 0.01, "Tin-can resonance of the droid's shell"),
    ("softness", "Softness", 4, 60, 1, "Attack time in ms: higher = rounder, cooing onsets"),
    ("brightness", "Brightness", 0.0, 1.0, 0.01, "Low-pass filter: lower = darker, softer on the ear"),
    ("space", "Room", 0.0, 1.0, 0.01, "Small room echo that softens and blends the voice"),
    ("glitch", "Glitches", 0.0, 1.0, 0.01, "Stutters and pitch jumps: a faulty motivator"),
]
PARAM_KEYS = [p[0] for p in PARAMS]
_LIMITS = {p[0]: (p[2], p[3]) for p in PARAMS}

# All presets share Songbird's clean, open timbre (no metal body, almost no overtones);
# each droid's character comes mainly from pitch, tempo, melody and attitude.
PRESETS = {
    "R2-D2 style": dict(pitch=1100, range=2.2, speed=1.0, syllable_ms=150, gap_ms=80, talk=1.0,
                        glide=4.0, steady=0.25, vib_rate=6.5, vib_depth=500, vib_share=0.45, trill=0.3,
                        attitude=0.15, brass=0.0, harmonics=0.1, ring=0.03, grit=0.0, noise=0.0, body=0.0,
                        softness=10, brightness=0.6, space=0.05, glitch=0.0),
    "R5 style": dict(pitch=820, range=1.5, speed=0.9, syllable_ms=165, gap_ms=85, talk=0.9,
                     glide=3.0, steady=0.35, vib_rate=5.0, vib_depth=350, vib_share=0.4, trill=0.2,
                     attitude=-0.1, brass=0.0, harmonics=0.15, ring=0.05, grit=0.05, noise=0.03, body=0.0,
                     softness=10, brightness=0.55, space=0.05, glitch=0.35),
    # Chopper: a grumpy, muted-horn voice rather than a whistle
    "Chopper style": dict(pitch=270, range=1.8, speed=1.0, syllable_ms=170, gap_ms=60, talk=1.2,
                          glide=2.5, steady=0.3, vib_rate=5.5, vib_depth=300, vib_share=0.35,
                          trill=0.0, attitude=-0.6, brass=1.0, harmonics=0.0, ring=0.0, grit=0.0,
                          noise=0.0, body=0.0, softness=14, brightness=0.8, space=0.04, glitch=0.0),
    "BB-8 style": dict(pitch=1250, range=1.1, speed=1.2, syllable_ms=85, gap_ms=40, talk=1.2,
                       glide=5.0, steady=0.15, vib_rate=7.0, vib_depth=200, vib_share=0.3, trill=0.3,
                       attitude=0.6, brass=0.0, harmonics=0.04, ring=0.0, grit=0.0, noise=0.0, body=0.0,
                       softness=22, brightness=0.55, space=0.06, glitch=0.0),
    "Songbird": dict(pitch=1500, range=1.6, speed=1.1, syllable_ms=110, gap_ms=55, talk=1.2,
                     glide=6.0, steady=0.1, vib_rate=8.0, vib_depth=300, vib_share=0.35, trill=0.45,
                     attitude=0.4, brass=0.0, harmonics=0.05, ring=0.0, grit=0.0, noise=0.0, body=0.0,
                     softness=12, brightness=0.6, space=0.08, glitch=0.0),
}
DEFAULT_VOICE = "R2-D2 style"
COMMAND_MOODS = ["ack", "error", "unknown", "ready", "chatter"]
# reactions to game events (kills, hits...) received through the game link
EVENT_MOODS = ["victory", "scared", "panic", "sad", "alarm", "greeting"]
# answers to questions ("are you ok?"): good news / bad news
ANSWER_MOODS = ["positive", "negative"]
MOODS = COMMAND_MOODS + EVENT_MOODS + ANSWER_MOODS


def complete(voice):
    """Fill missing parameters from the default voice and clamp to valid ranges."""
    v = dict(PRESETS[DEFAULT_VOICE])
    for k, val in (voice or {}).items():
        if k in _LIMITS:
            lo, hi = _LIMITS[k]
            v[k] = float(min(hi, max(lo, val)))
    return v


# ----------------------------------------------------------------- building blocks
def _spectral_filter(y, gain_fn):
    Y = np.fft.rfft(y)
    f = np.fft.rfftfreq(len(y), 1 / SR)
    return np.fft.irfft(Y * gain_fn(np.maximum(f, 1.0)), len(y))


def _band_noise(rng, n, lo, hi):
    y = _spectral_filter(rng.standard_normal(n),
                         lambda f: 1 / np.sqrt(1 + (f / hi) ** 4) / np.sqrt(1 + (lo / f) ** 4))
    return y / (np.abs(y).max() + 1e-9)


def _ramps(n, attack_ms, release_ms):
    e = np.ones(n)
    a = min(n // 2, int(SR * attack_ms / 1000))
    r = min(n - a, int(SR * release_ms / 1000))
    if a:
        e[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    if r:
        e[-r:] = np.cos(np.linspace(0, np.pi / 2, r)) ** 2
    return e


def _smooth_dip(n, rng, depth=1.0):
    """Hann-shaped gain dip (used for glitch stutters instead of hard cuts)."""
    w = np.hanning(n)
    return 1 - depth * w


class _Voice:
    def __init__(self, voice, rng):
        self.v = complete(voice)
        self.rng = rng

    # pitch position -1..1 inside the voice range -> Hz
    def hz(self, pos):
        v = self.v
        return float(np.clip(v["pitch"] * 2 ** (pos * v["range"] / 2), 60, 4200))

    def dur(self, scale=1.0):
        v, r = self.v, self.rng
        d = v["syllable_ms"] / 1000 * np.exp(r.normal(0, 0.45)) * scale / v["speed"]
        return float(np.clip(d, 0.04, 1.2))

    def gap(self):
        v, r = self.v, self.rng
        return float(np.clip(v["gap_ms"] / 1000 * np.exp(r.normal(0, 0.5)) / v["speed"], 0.01, 0.6))

    def direction(self, bias=0.0):
        p_rise = np.clip(0.5 + 0.3 * self.v["attitude"] + bias, 0.05, 0.95)
        return 1 if self.rng.random() < p_rise else -1

    def syllable(self, pos=None, kind=None, direction=None, scale=1.0, **extra):
        """Describe one syllable (rendered later)."""
        v, r = self.v, self.rng
        if pos is None:
            pos = float(np.clip(r.normal(0.1 * v["attitude"], 0.6), -1, 1))
        if kind is None:
            u = r.random()
            kind = "steady" if u < v["steady"] else ("arch" if r.random() < 0.3 else "glide")
        whoop = kind == "glide" and r.random() < 0.18     # very fast, short sweep
        d = self.dur(scale * (0.6 if whoop else 1.0))
        f0 = self.hz(pos)
        sweep = v["glide"] * d * r.uniform(0.5, 1.5) * (r.uniform(3, 5) if whoop else 1)
        direction = direction if direction is not None else self.direction()
        f1 = float(np.clip(f0 * 2 ** (direction * sweep), 60, 4500))
        peak = float(np.clip(f0 * 2 ** (abs(sweep) * r.uniform(0.6, 1.2) * self.direction()), 60, 4500))
        s = dict(kind=kind, f0=f0, f1=f1, peak=peak, dur=d, vib=None, grit=0.0, harm=0.0, gain=1.0)
        if r.random() < v["trill"] * (1 - 0.8 * v["brass"]):   # fast trills sound rude on a low voice
            s["vib"] = (r.uniform(14, 24), r.uniform(120, 300))
        elif r.random() < v["vib_share"]:
            s["vib"] = (v["vib_rate"] * r.uniform(0.8, 1.25), v["vib_depth"] * r.uniform(0.6, 1.3))
        s.update(extra)
        return s

    # ---------------------------------------------------------------- moods
    def plan(self, mood):
        v, r = self.v, self.rng
        talk = v["talk"]

        def count(lo, hi):
            return max(1, int(round(r.integers(lo, hi + 1) * talk)))

        if mood == "ack":                      # positive: ends on a rising high note
            syl = [self.syllable(scale=0.8) for _ in range(count(1, 2))]
            syl.append(self.syllable(pos=r.uniform(-0.1, 0.4), kind="glide", direction=1, scale=0.9))
        elif mood == "error":                  # low, falling, ends with a soft grumble
            syl = [self.syllable(pos=r.uniform(-0.6, 0.2), direction=-1, scale=0.9)
                   for _ in range(count(1, 2))]
            if v["brass"] > 0.5:               # vocal voices: a sulky falling "uooo", no "brrr"
                syl.append(self.syllable(pos=-0.4, kind="glide", direction=-1, scale=2.0,
                                         vib=(r.uniform(4.5, 6), r.uniform(150, 250)), gain=0.9))
            else:
                syl.append(self.syllable(pos=-1.0, kind="glide", direction=-1, scale=2.0,
                                         vib=(r.uniform(15, 20), r.uniform(120, 220)),
                                         grit=0.15, harm=0.15, gain=0.85))
        elif mood == "unknown":                # quick mumble, then a long questioning rise
            syl = [self.syllable(pos=r.uniform(-0.5, 0.2), scale=0.6) for _ in range(count(1, 2))]
            syl.append(self.syllable(pos=r.uniform(-0.6, -0.2), kind="glide", direction=1, scale=2.0,
                                     vib=(r.uniform(4.5, 6.5), r.uniform(200, 380))))
        elif mood == "ready":                  # bright ascending beeps and a trill
            steps = np.linspace(-0.3, 0.6, count(2, 3))
            syl = [self.syllable(pos=p, kind="steady", scale=0.6, vib=None) for p in steps]
            syl.append(self.syllable(pos=0.8, kind="glide", direction=1, scale=0.8,
                                     vib=(r.uniform(16, 22), 200)))
        elif mood == "victory":                # excited, climbing whoops ending in a high trill
            steps = np.linspace(-0.2, 0.9, count(3, 4))
            syl = [self.syllable(pos=p, kind="glide", direction=1, scale=0.55) for p in steps]
            syl.append(self.syllable(pos=1.0, kind="steady", scale=1.1, vib=(r.uniform(16, 22), 260)))
        elif mood == "scared":                 # a sudden high squeal sliding down, trembling
            syl = [self.syllable(pos=0.9, kind="glide", direction=-1, scale=0.9,
                                 vib=(r.uniform(11, 15), r.uniform(220, 320)))]
            if r.random() < 0.6:
                syl.append(self.syllable(pos=0.3, kind="glide", direction=-1, scale=0.5,
                                         vib=(r.uniform(11, 15), 200)))
        elif mood == "panic":                  # a rapid string of falling shrieks
            syl = [self.syllable(pos=r.uniform(0.5, 1.0), kind="glide", direction=-1, scale=0.45,
                                 vib=(r.uniform(12, 18), 250)) for _ in range(count(4, 6))]
        elif mood == "sad":                    # a slow, low, drooping moan
            syl = [self.syllable(pos=r.uniform(-0.1, 0.2), kind="glide", direction=-1, scale=1.8,
                                 vib=(r.uniform(4, 5.5), 180))]
            syl.append(self.syllable(pos=-0.6, kind="glide", direction=-1, scale=2.2,
                                     vib=(r.uniform(3.5, 5), 220), gain=0.8))
        elif mood == "alarm":                  # two-tone warning beeps
            hi, lo = r.uniform(0.5, 0.8), r.uniform(-0.3, 0.0)
            syl = [self.syllable(pos=p, kind="steady", scale=0.7, vib=None)
                   for p in [hi, lo] * count(2, 3)]
        elif mood == "positive":               # a bright, bouncy "yep!": two quick rising notes
            syl = [self.syllable(pos=0.1, kind="steady", scale=0.45, vib=None),
                   self.syllable(pos=0.55, kind="glide", direction=1, scale=0.7, vib=None)]
        elif mood == "negative":               # a low "uh-uh": two falling notes, the second longer
            syl = [self.syllable(pos=-0.1, kind="steady", scale=0.5, vib=None),
                   self.syllable(pos=-0.5, kind="glide", direction=-1, scale=1.2,
                                 vib=(r.uniform(5, 7), 150))]
        elif mood == "greeting":               # a friendly "hel-lo!" and a little chatter
            syl = [self.syllable(pos=-0.1, kind="steady", scale=0.6, vib=None),
                   self.syllable(pos=0.4, kind="glide", direction=1, scale=0.9)]
            syl += [self.syllable(scale=0.6) for _ in range(count(1, 2))]
        else:                                  # chatter / any custom mood
            syl = [self.syllable() for _ in range(count(3, 6))]
        return syl

    # --------------------------------------------------------------- render
    def render_syllable(self, s):
        v, r = self.v, self.rng
        n = max(64, int(s["dur"] * SR))
        t = np.arange(n) / SR
        x = t / s["dur"]
        l0, l1, lp = np.log2(s["f0"]), np.log2(s["f1"]), np.log2(s["peak"])
        if s["kind"] == "steady":
            lf = l0 + 0.008 * np.sin(2 * np.pi * 1.5 * t)
        elif s["kind"] == "arch":            # quadratic Bezier f0 -> peak -> f1
            lf = (1 - x) ** 2 * l0 + 2 * (1 - x) * x * lp + x ** 2 * l1
        else:                                # eased glide, like a bird's slur
            e = x ** r.uniform(0.7, 1.4)
            lf = l0 + (l1 - l0) * (3 * e ** 2 - 2 * e ** 3)
        if s["vib"]:
            rate, depth = s["vib"]
            # vibrato fades in, as a singer (or a bird) would do
            fade = np.clip(t / 0.04, 0, 1)
            lf = lf + fade * depth / 1200 / 2 * np.sin(2 * np.pi * rate * t + r.uniform(0, 6.28))
        if v["glitch"] and r.random() < v["glitch"] * 0.6:   # pitch jump, with a quick slur
            tj = s["dur"] * r.uniform(0.3, 0.7)
            jump = r.choice([-1, 1]) * r.uniform(0.3, 0.9)
            lf = lf + jump * 0.5 * (1 + np.tanh((t - tj) / 0.006))
        brass = v["brass"]
        if brass:
            # lip "scoop": horn notes start flat and slide up
            lf = lf - r.uniform(0.08, 0.2) * brass * np.exp(-t / 0.035)
            # unsteady pitch, like a grumbling voice: smooth random wander (~10 Hz)
            knots = r.standard_normal(int(s["dur"] * 10) + 3)
            wander = np.interp(np.linspace(0, len(knots) - 1, n), np.arange(len(knots)), knots)
            lf = lf + brass * 0.012 * wander
        f = np.clip(2 ** lf, 60, 5000)
        ph = 2 * np.pi * np.cumsum(f) / SR

        # bell-shaped envelope for short chirps, soft ramps for longer notes
        if s["dur"] < 0.13:
            env = np.sin(np.pi * x) ** 1.5
        else:
            env = _ramps(n, max(8.0, v["softness"]), max(35.0, 2 * v["softness"]))
        env *= 1 + 0.06 * np.sin(2 * np.pi * 3.5 * t)

        # whistle: a near-pure sine, plus band-limited overtones (no aliasing)
        h = min(1.0, v["harmonics"] + s["harm"])
        sig = np.sin(ph)
        if h:
            for k, a in ((2, 0.30), (3, 0.12), (4, 0.05)):
                sig = sig + h * a * np.clip((7500 - k * f) / 2500, 0, 1) * np.sin(k * ph)
        if v["ring"]:                       # gentle FM shimmer
            ring = v["ring"]
            sig = (1 - 0.5 * ring) * sig + 0.5 * ring * np.sin(ph + 1.1 * ring * np.sin(1.5 * ph))
        if brass:                           # blend towards the horn timbre
            sig = (1 - brass) * sig / (np.abs(sig).max() + 1e-9) + brass * self.horn(f, ph, t, env, s)
        g = min(1.0, v["grit"] + s["grit"])
        if g:                               # soft saturation (the low-pass tames it later)
            drive = 1 + 4 * g
            sig = np.tanh(drive * sig) / np.tanh(drive)
        if v["noise"]:                      # gear grinding: low band, smooth modulation
            grind = _band_noise(r, n, 250, 2200)
            grind *= 0.6 + 0.4 * np.sin(2 * np.pi * r.uniform(22, 40) * t)
            sig = sig + v["noise"] * 0.3 * grind
        # the ear is most sensitive around 2-5 kHz: keep high whistles from piercing
        comp = np.clip((f / 1000.0) ** -0.45, 0.4, 1.0)
        return sig * env * comp * s["gain"] * r.uniform(0.8, 1.0)

    # Spectral envelope of a hummed, grumbled "oooo" (frequency Hz, level dB), measured on
    # the voiced parts of a reference grumpy-droid voice: almost all the energy sits in the
    # first two harmonics, the rest falls steeply. That is what makes it round and
    # harmonic instead of croaky.
    ENVELOPE = ((80, -4), (250, 0), (420, -2), (600, -8), (850, -16), (1200, -19),
                (1600, -22), (2200, -26), (3000, -30), (4500, -36), (7000, -50))
    # the mouth shape moves the envelope: "u" is darker, an open "o" a little brighter
    VOWEL_SHIFT = (0.8, 1.0, 1.2)

    def horn(self, f, ph, t, env, s):
        """Human-like vowel ("uoooo"): harmonics weighted by the measured spectral
        envelope. The mouth opens with loudness, gliding u -> o -> open o, as a person
        saying "uoooo". Grit adds a touch of breath."""
        r = self.rng
        n = len(f)
        opening = np.clip(env, 0, 1) ** 0.8 * r.uniform(0.7, 1.0)
        shift = np.interp(opening, (0.0, 0.6, 1.0), self.VOWEL_SHIFT)
        ef = np.log2([p[0] for p in self.ENVELOPE])
        ed = np.array([p[1] for p in self.ENVELOPE], dtype=float)
        out = np.zeros(n)
        kmax = int(min(30, 6000 / max(60.0, f.min())))
        phases = r.uniform(0, 2 * np.pi, kmax + 1)     # scattered phases: a round waveform
        phases[1] = 0
        for k in range(1, kmax + 1):
            fk = k * f
            db = np.interp(np.log2(fk / shift), ef, ed)
            gain = 10 ** (db / 20) * np.clip((7000 - fk) / 1500, 0, 1)
            out += gain * np.sin(k * ph + phases[k])
        out /= np.abs(out).max() + 1e-9
        g = self.v["grit"]
        if g:                                # a touch of breath only; no growl (it sounds rude)
            breath = _band_noise(r, n, 400, 3000) * (0.5 + 0.5 * np.cos(ph)) ** 6
            out = out + 0.1 * g * breath
        return out / (np.abs(out).max() + 1e-9)

    def servo(self):
        """Short motor whir (used by noisy voices before speaking)."""
        r = self.rng
        n = int(SR * r.uniform(0.08, 0.16))
        t = np.arange(n) / SR
        f = r.uniform(160, 260) * 2 ** (t / t[-1] * r.uniform(0.5, 1.0))
        whir = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.6 + _band_noise(r, n, 400, 2500) * 0.4
        return whir * _ramps(n, 20, 40) * 0.35

    def render(self, mood):
        v, r = self.v, self.rng
        parts = []
        if v["noise"] > 0.3 and r.random() < v["noise"]:
            parts += [self.servo(), np.zeros(int(SR * 0.02))]
        plan = self.plan(mood)
        for i, s in enumerate(plan):
            parts.append(self.render_syllable(s))
            if i < len(plan) - 1:
                parts.append(np.zeros(int(SR * self.gap())))
        y = np.concatenate(parts)
        if v["glitch"]:                       # stutters: short smooth dropouts
            for _ in range(int(r.poisson(v["glitch"] * 3))):
                w = int(SR * r.uniform(0.012, 0.03))
                a = int(r.uniform(0, max(1, len(y) - w)))
                y[a:a + w] *= _smooth_dip(len(y[a:a + w]), r, 0.95)
        if v["body"]:                         # metallic shell: light feed-forward comb
            d = int(SR * 0.0042)
            b = v["body"]
            z = y.copy()
            z[d:] += 0.35 * b * y[:-d]
            z[2 * d:] += 0.18 * b * y[:-2 * d]
            z[3 * d:] += 0.08 * b * y[:-3 * d]
            y = z
        tail = int(SR * (0.05 + 0.15 * v["space"]))
        y = np.concatenate([np.zeros(int(SR * 0.005)), y, np.zeros(tail)])
        # brightness: 2nd-order low-pass; also cut sub-bass rumble
        fc = 1600 * 2 ** (v["brightness"] * 2.5)
        hp = 150 - 100 * v["brass"]           # keep the low fundamental of horn voices
        y = _spectral_filter(y, lambda f: 1 / np.sqrt(1 + (f / fc) ** 4) / np.sqrt(1 + (hp / f) ** 4))
        if v["space"]:                        # small, close room (short decay = no "distance")
            n = int(SR * 0.25)
            t = np.arange(n) / SR
            decay = 0.025 + 0.06 * v["space"]
            ir = r.standard_normal(n) * np.exp(-t / decay)
            ir = _spectral_filter(ir, lambda f: 1 / np.sqrt(1 + (f / 4000) ** 2))
            ir[: int(SR * 0.004)] = 0         # pre-delay
            m = len(y) + n
            wet = np.fft.irfft(np.fft.rfft(y, m) * np.fft.rfft(ir, m), m)[: len(y)]
            dry_rms = np.sqrt((y ** 2).mean()) + 1e-9
            wet *= dry_rms / (np.sqrt((wet ** 2).mean()) + 1e-9)
            y = y + 0.3 * v["space"] * wet
        # loudness: normalise the voiced part to a comfortable RMS, never above PEAK_LIMIT
        peak = np.abs(y).max() + 1e-9
        voiced = y[np.abs(y) > 0.05 * peak]
        rms = np.sqrt((voiced ** 2).mean()) + 1e-9
        y = y * min(TARGET_RMS / rms, PEAK_LIMIT / peak)
        return y.astype(np.float32)


def make(mood, seed=None, voice=None):
    """Synthesize one utterance. Returns (samples float32, sample_rate)."""
    rng = np.random.default_rng(seed)
    return _Voice(voice, rng).render(mood), SR
