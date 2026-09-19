"""The app's preamp, built from the EQ bands (spec §4.4).

The CHU 2 has no usable preamp register (tests #19, #20), so a boost is made
safe inside the bands themselves, in this order:

1. **Shelf flip** (free, exact): a low shelf +G dB at f has exactly the shape of
   a high shelf -G dB at f, G dB louder (and the same the other way round).
   Storing the opposite cut keeps the sound and lowers the level by G.
2. **Trim band**: if the curve still goes above 0 dB, a free band (0 dB) becomes
   a high shelf at 20 Hz, a nearly flat cut, with its gain found so the whole
   curve, trim included, stays <= 0 dB (0.5 dB steps, never below -12 dB).
3. **No free band**: the result carries the warning ``"no_free_band"``.

:func:`compute` never changes its input; it returns the bands to send to the
CHU 2 plus the numbers the UI shows.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import eq

TRIM_FREQUENCY_HZ = 20.0
TRIM_Q = 0.707
TRIM_STEP_DB = 0.5
TRIM_LIMIT_DB = -12.0
_EPS = 1e-6
_GRID = [round(f, 3) for f in eq.log_frequency_axis(20.0, 20_000.0, 481)]
_OPPOSITE = {"low_shelf": "high_shelf", "high_shelf": "low_shelf"}


@dataclasses.dataclass
class PreampResult:
    bands: List[eq.FilterBand]  # what the CHU 2 plays and stores (5 bands)
    preamp_db: float            # total level change from flips and trim, <= 0
    peak_db: float              # highest point of the EQ as designed ("max boost")
    peak_hz: float              # where that point is
    device_peak_db: float       # highest point of what the CHU 2 plays
    method: str                 # "none" | "flip" | "trim" | "flip+trim"
    flipped: List[int]          # band indexes stored as the opposite shelf
    trim_index: Optional[int]   # band index that holds the trim, if any
    warning: Optional[str]      # None | "no_free_band" | "trim_limit" | "stored_without_preamp"

    def to_dict(self) -> Dict[str, Any]:
        """Everything but the bands, rounded for display (JSON-friendly)."""
        return {
            "preamp_db": round(self.preamp_db, 1),
            "peak_db": round(self.peak_db, 2),
            "peak_hz": round(self.peak_hz),
            "device_peak_db": round(self.device_peak_db, 2),
            "method": self.method,
            "flipped": list(self.flipped),
            "trim_index": self.trim_index,
            "warning": self.warning,
        }


# ---- curve helpers ---------------------------------------------------------- #
def _grid(bands: Sequence[eq.FilterBand]) -> List[float]:
    """The log grid plus each band's own frequency (where peaks sit)."""
    extra = {b.frequency for b in bands if 20.0 <= b.frequency <= 20_000.0}
    return sorted(set(_GRID) | extra)


def curve_db(bands: Sequence[eq.FilterBand], freqs: Sequence[float]) -> List[float]:
    return eq.Equalizer(list(bands)).magnitude_response_db(freqs)


def peak(bands: Sequence[eq.FilterBand]) -> Tuple[float, float]:
    """(highest level in dB, its frequency in Hz) of the combined curve, 20 Hz-20 kHz."""
    freqs = _grid(bands)
    levels = curve_db(bands, freqs)
    top = max(range(len(levels)), key=levels.__getitem__)
    return levels[top], freqs[top]


def flip_shelf(band: eq.FilterBand) -> eq.FilterBand:
    """The opposite shelf with the opposite gain: same shape, ``band.gain`` dB quieter."""
    return eq.FilterBand(_OPPOSITE[band.type], band.frequency, -band.gain, band.q)


# ---- the preamp ------------------------------------------------------------- #
def compute(bands: Sequence[eq.FilterBand], auto: bool = True) -> PreampResult:
    """Work out the bands to store so the curve stays <= 0 dB (spec §4.4)."""
    design = [dataclasses.replace(b) for b in bands]
    peak_db, peak_hz = peak(design)
    if not auto or peak_db <= _EPS:
        return PreampResult(design, 0.0, peak_db, peak_hz, peak_db, "none", [], None, None)

    flipped = _choose_flips(design, peak_db)
    device = list(design)
    for i in flipped:
        device[i] = flip_shelf(design[i])
    preamp_db = -sum(design[i].gain for i in flipped)
    device_peak, _hz = peak(device)
    method = "flip" if flipped else "none"
    trim_index: Optional[int] = None
    warning: Optional[str] = None

    if device_peak > _EPS:
        free = [i for i, b in enumerate(device) if b.gain == 0]
        if not free:
            warning = "no_free_band"
        else:
            trim_index = free[-1]  # the highest-numbered free band
            trim_db, device_peak = _fit_trim(device, device_peak)
            device[trim_index] = eq.FilterBand("high_shelf", TRIM_FREQUENCY_HZ, trim_db, TRIM_Q)
            preamp_db += trim_db
            method = "flip+trim" if flipped else "trim"
            if device_peak > _EPS:
                warning = "trim_limit"

    return PreampResult(device, round(preamp_db, 1), peak_db, peak_hz, device_peak,
                        method, flipped, trim_index, warning)


def _choose_flips(bands: Sequence[eq.FilterBand], peak_db: float) -> List[int]:
    """The shelf boosts to flip: the set with the smallest total gain that
    covers the whole peak (fewest flips on a tie), else every shelf boost."""
    boosts = [i for i, b in enumerate(bands) if b.type in _OPPOSITE and b.gain > 0]
    best: Optional[Tuple[float, List[int]]] = None
    for size in range(1, len(boosts) + 1):
        for combo in itertools.combinations(boosts, size):
            total = sum(bands[i].gain for i in combo)
            if total >= peak_db - _EPS and (best is None or total < best[0] - _EPS):
                best = (total, list(combo))
    return best[1] if best is not None else boosts


def _fit_trim(device: Sequence[eq.FilterBand], device_peak: float) -> Tuple[float, float]:
    """Smallest trim (0.5 dB steps, away from zero, >= -12 dB) that keeps the
    curve <= 0 dB; returns (trim gain, resulting peak). The trim slot is 0 dB
    in ``device``, so it adds nothing to the base curve."""
    freqs = _grid(device)
    base = curve_db(device, freqs)
    trim = -math.ceil(round(device_peak / TRIM_STEP_DB, 9)) * TRIM_STEP_DB
    while True:
        trim = max(trim, TRIM_LIMIT_DB)
        shape = curve_db([eq.FilterBand("high_shelf", TRIM_FREQUENCY_HZ, trim, TRIM_Q)], freqs)
        top = max(b + s for b, s in zip(base, shape))
        if top <= _EPS or trim <= TRIM_LIMIT_DB:
            return trim, top
        trim -= TRIM_STEP_DB
