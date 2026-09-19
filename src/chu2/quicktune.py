"""Quick Tune: plain-English goals as five-band recipes (brief §4, spec §5).

Rules (brief §4): values are for the CHU 2 DSP with its EQ flat; unlisted slots
stay at their idle defaults at 0 dB. A **scene** sets all five slots and scenes
are exclusive. A **tweak** owns its slot(s); tweaks combine, except two that
own the same slot. **Intensity** scales gains (x0.5 / x1 / x1.5); boosts are
capped at +6 dB and cuts at -8 dB. Every recipe still needs a listening check
on a CHU 2 DSP before it ships (brief §4 "Validation").
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Brief §3.5 idle slots: Bass, Body, Voice, Detail, Air (all 0 dB).
IDLE_DESIGN: List[Dict[str, Any]] = [
    {"type": "low_shelf", "frequency": 105.0, "gain": 0.0, "q": 0.71, "bypass": False},
    {"type": "peaking", "frequency": 250.0, "gain": 0.0, "q": 1.0, "bypass": False},
    {"type": "peaking", "frequency": 1000.0, "gain": 0.0, "q": 1.0, "bypass": False},
    {"type": "peaking", "frequency": 4000.0, "gain": 0.0, "q": 1.4, "bypass": False},
    {"type": "high_shelf", "frequency": 10000.0, "gain": 0.0, "q": 0.71, "bypass": False},
]
INTENSITY = {"subtle": 0.5, "standard": 1.0, "strong": 1.5}
MAX_BOOST_DB = 6.0
MAX_CUT_DB = -8.0
GAMING_NOTE = ("EQ changes how loud each part of the sound is. It can make quiet cues like footsteps "
               "less buried under explosions. It can't add direction or distance that isn't in the "
               "game's audio, and it doesn't replace in-game headphone/HRTF settings.")


def _b(kind: str, frequency: float, gain: float, q: float) -> Dict[str, Any]:
    return {"type": kind, "frequency": float(frequency), "gain": float(gain), "q": float(q)}


# slot number (1-5) -> band; slots not listed stay idle. The five scenes are
# the owner's profiles (2026-09-19, brief §4): gentle, because the CHU 2 DSP's
# stock tuning is already close to neutral.
SCENES: List[Dict[str, Any]] = [
    {"id": "music", "name": "Music (warm and clear)", "tags": ["Music"], "gaming": False,
     "slots": {1: _b("low_shelf", 90, 2.0, 0.70), 2: _b("peaking", 250, -0.8, 1.00),
               3: _b("peaking", 2800, -1.5, 1.20), 4: _b("peaking", 7500, -2.0, 2.00),
               5: _b("high_shelf", 12000, 1.0, 0.70)},
     "about": ("Adds a little bass weight below 90 Hz, eases vocal glare around 2.8 kHz and smooths "
               "'s' sounds and cymbals around 7.5 kHz, with a touch of air. Made to leave on.")},
    {"id": "gaming", "name": "Gaming (League, RPG, MMO)", "tags": ["Gaming"], "gaming": True,
     "slots": {1: _b("low_shelf", 80, 1.0, 0.70), 2: _b("peaking", 220, -1.5, 1.00),
               3: _b("peaking", 1700, 1.0, 1.00), 4: _b("peaking", 3500, 1.0, 1.20),
               5: _b("peaking", 7000, -1.0, 2.00)},
     "about": ("Trims the muddy 220 Hz region by 1.5 dB and lifts 1.7–3.5 kHz by 1 dB, so dialogue, "
               "spells and UI cues stand out, and keeps a little bass for atmosphere.")},
    {"id": "movies", "name": "Movies (cinematic)", "tags": ["Movies"], "gaming": False,
     "slots": {1: _b("low_shelf", 65, 3.0, 0.70), 2: _b("peaking", 250, -1.0, 1.00),
               3: _b("peaking", 1800, 1.0, 1.00), 4: _b("peaking", 3200, 1.0, 1.20),
               5: _b("peaking", 7500, -1.5, 2.00)},
     "about": ("Adds up to 3 dB of rumble below 65 Hz for scores and explosions and lifts 1.8–3.2 kHz "
               "by 1 dB, so speech stays clear. If voices feel distant, try Subtle.")},
    {"id": "fps", "name": "Competitive FPS", "tags": ["Gaming"], "gaming": True,
     "slots": {1: _b("low_shelf", 100, -2.5, 0.70), 2: _b("peaking", 250, -2.0, 1.00),
               3: _b("peaking", 1600, 1.5, 1.00), 4: _b("peaking", 3200, 2.0, 1.20),
               5: _b("peaking", 7000, -1.0, 2.00)},
     "about": ("Lowers the bass below 100 Hz by 2.5 dB and 250 Hz by 2 dB, and lifts 1.6–3.2 kHz by up "
               "to 2 dB, so footsteps and reloads are less buried. Leaner on purpose.")},
    {"id": "calls", "name": "Calls", "tags": ["Calls"], "gaming": False,
     "slots": {1: _b("low_shelf", 120, -2.0, 0.70), 2: _b("peaking", 300, -1.5, 1.00),
               3: _b("peaking", 1600, 1.0, 1.00), 4: _b("peaking", 2700, 1.5, 1.20),
               5: _b("peaking", 7000, -1.5, 2.00)},
     "about": ("Trims boom below 300 Hz and lifts 1.6–2.7 kHz by up to 1.5 dB, so voices on calls are "
               "clearer and less tiring. It changes what you hear, not your microphone.")},
]

TWEAKS: List[Dict[str, Any]] = [
    {"id": "sub_bass", "name": "More sub-bass", "slots": {1: _b("low_shelf", 55, 4.0, 0.71)},
     "about": "Adds up to 4 dB below ~55 Hz (rumble and kick weight) and leaves mid-bass and vocals alone."},
    {"id": "clean_bass", "name": "Cleaner bass (less boom)", "slots": {2: _b("peaking", 200, -2.5, 0.90)},
     "about": "Removes 2.5 dB around 200 Hz, so bass sounds tighter and less boomy without losing sub-bass."},
    {"id": "softer_vocals", "name": "Softer vocals", "slots": {3: _b("peaking", 3000, -3.0, 1.00)},
     "about": "Pulls the 2–4 kHz 'shout' region down by up to 3 dB so voices sit slightly further back."},
    {"id": "clearer_voices", "name": "Clearer voices", "slots": {3: _b("peaking", 1600, 2.0, 1.00)},
     "about": "Lifts 1–2.5 kHz by up to 2 dB so speech consonants cut through; can sound a little forward."},
    {"id": "less_sharp", "name": "Less sharp cymbals",
     "slots": {4: _b("peaking", 7000, -2.5, 2.00), 5: _b("high_shelf", 10000, -1.0, 0.71)},
     "about": "Tames the 6–8 kHz 'tss' by 2.5 dB and eases the top octave by 1 dB. Detail stays, splash goes."},
    {"id": "sparkle", "name": "More sparkle", "slots": {5: _b("high_shelf", 10000, 2.0, 0.71)},
     "about": "Adds 2 dB of 'air' above 10 kHz. How much you hear depends on fit and ear tips."},
]

_SCENES = {s["id"]: s for s in SCENES}
_TWEAKS = {t["id"]: t for t in TWEAKS}


def scale(gain: float, intensity: str) -> float:
    """Gain at an intensity, capped (+6 / -8 dB) and rounded to 0.1 dB, halves
    away from zero (5.25 -> 5.3), as the page's own rounding does."""
    value = min(max(gain * INTENSITY[intensity], MAX_CUT_DB), MAX_BOOST_DB)
    tenths = math.floor(abs(value) * 10 + 0.5 + 1e-9)
    return math.copysign(tenths / 10, value) + 0.0


def conflicts(tweak_id: str) -> List[str]:
    """Tweaks that own one of the same slots (they work as a radio pair)."""
    slots = set(_TWEAKS[tweak_id]["slots"])
    return [t["id"] for t in TWEAKS if t["id"] != tweak_id and slots & set(t["slots"])]


def compose(scene_id: Optional[str], tweak_ids: Sequence[str],
            intensity: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """(five design bands, notes) for a scene, tweaks and an intensity."""
    if intensity not in INTENSITY:
        raise ValueError(f"unknown intensity {intensity!r}")
    if scene_id is not None and scene_id not in _SCENES:
        raise ValueError(f"unknown scene {scene_id!r}")
    for tweak_id in tweak_ids:
        if tweak_id not in _TWEAKS:
            raise ValueError(f"unknown tweak {tweak_id!r}")
        if set(conflicts(tweak_id)) & set(tweak_ids):
            raise ValueError(f"tweak {tweak_id!r} shares a band with another chosen tweak")
    design = [dict(b) for b in IDLE_DESIGN]
    scene = _SCENES.get(scene_id) if scene_id else None
    if scene:
        for slot, band in scene["slots"].items():
            design[slot - 1] = dict(band, gain=scale(band["gain"], intensity), bypass=False)
    notes = []
    for tweak_id in tweak_ids:
        for slot, band in sorted(_TWEAKS[tweak_id]["slots"].items()):
            if scene and slot in scene["slots"]:
                notes.append(f"Replaces band {slot} of {scene['name']}.")
            design[slot - 1] = dict(band, gain=scale(band["gain"], intensity), bypass=False)
    return design, notes


def explain(scene_id: Optional[str], tweak_ids: Sequence[str]) -> List[str]:
    """The "what changed" sentences, plus the gaming note for a gaming scene."""
    text = []
    scene = _SCENES.get(scene_id) if scene_id else None
    if scene:
        text.append(scene["about"])
    text.extend(_TWEAKS[t]["about"] for t in tweak_ids)
    if scene and scene["gaming"]:
        text.append(GAMING_NOTE)
    return text


def recipes() -> Dict[str, Any]:
    """Scenes, tweaks and intensities for the page (JSON-friendly)."""
    def public(recipe: Dict[str, Any]) -> Dict[str, Any]:
        return {"id": recipe["id"], "name": recipe["name"], "about": recipe["about"],
                "slots": sorted(recipe["slots"]), "tags": recipe.get("tags", []),
                "gaming": recipe.get("gaming", False)}
    return {"scenes": [public(s) for s in SCENES],
            "tweaks": [dict(public(t), conflicts=conflicts(t["id"])) for t in TWEAKS],
            "intensities": list(INTENSITY)}
