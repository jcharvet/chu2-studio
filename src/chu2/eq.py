"""Parametric EQ model and RBJ biquad filter math.

The DSP protocol is still being reverse-engineered, but the *meaning* of an EQ
preset — a list of filter bands — is well defined. This module implements the
RBJ audio-EQ-cookbook biquad equations so presets can be:

* validated (frequency/Q/gain ranges),
* previewed (composite magnitude response), and
* exported (EqualizerAPO config, coefficients).

All of this works fully offline, with no device attached.
"""

from __future__ import annotations

import cmath
import dataclasses
import math
from typing import Iterable, List, Sequence, Tuple

#: Default sample rate used when a preset does not specify one. 48 kHz is the
#: common native rate for USB audio class devices.
DEFAULT_SAMPLE_RATE: int = 48_000

#: Human-readable name -> RBJ filter selector.
FILTER_TYPES: Tuple[str, ...] = (
    "peaking",
    "low_shelf",
    "high_shelf",
    "lowpass",
    "highpass",
    "bandpass",
    "notch",
    "allpass",
)

#: EqualizerAPO filter codes for each supported type.
EQUALIZER_APO_CODES = {
    "peaking": "PK",
    "low_shelf": "LSC",
    "high_shelf": "HSC",
    "lowpass": "LP",
    "highpass": "HP",
    "bandpass": "BP",
    "notch": "NO",
    "allpass": "AP",
}


@dataclasses.dataclass
class FilterBand:
    """A single parametric EQ band."""

    type: str = "peaking"
    frequency: float = 1000.0
    gain: float = 0.0  # dB
    q: float = 1.0

    def __post_init__(self) -> None:
        if self.type not in FILTER_TYPES:
            raise ValueError(
                f"Unknown filter type {self.type!r}. Expected one of {FILTER_TYPES}."
            )
        if self.frequency <= 0:
            raise ValueError("frequency must be > 0 Hz")
        if self.q <= 0:
            raise ValueError("Q must be > 0")


@dataclasses.dataclass
class Biquad:
    """Normalized biquad coefficients (a0 is assumed to be 1)."""

    b0: float
    b1: float
    b2: float
    a1: float
    a2: float

    def apply(self, samples: Sequence[float]) -> List[float]:
        """Apply this biquad to a mono signal in-place via Direct Form II."""
        z1 = 0.0
        z2 = 0.0
        out: List[float] = []
        for x in samples:
            y = self.b0 * x + z1
            z1 = self.b1 * x - self.a1 * y + z2
            z2 = self.b2 * x - self.a2 * y
            out.append(y)
        return out

    def response(self, frequency: float, sample_rate: int) -> complex:
        """Return the complex frequency response H(e^{jw}) at ``frequency`` Hz."""
        w = 2.0 * math.pi * frequency / sample_rate
        z_inv = cmath.exp(-1j * w)
        num = self.b0 + self.b1 * z_inv + self.b2 * z_inv * z_inv
        den = 1.0 + self.a1 * z_inv + self.a2 * z_inv * z_inv
        return num / den


@dataclasses.dataclass
class Equalizer:
    """An ordered list of bands applied at a given sample rate."""

    bands: List[FilterBand]
    sample_rate: int = DEFAULT_SAMPLE_RATE

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be > 0")

    def coefficients(self) -> List[Biquad]:
        return [band_coefficients(band, self.sample_rate) for band in self.bands]

    def magnitude_response_db(self, frequencies: Sequence[float]) -> List[float]:
        """Composite magnitude response (dB) at each frequency."""
        biquads = self.coefficients()
        out: List[float] = []
        for f in frequencies:
            mag = 1.0
            for biquad in biquads:
                mag *= abs(biquad.response(f, self.sample_rate))
            out.append(20.0 * math.log10(mag + 1e-12))
        return out


# --------------------------------------------------------------------------- #
# RBJ biquad coefficient generation
# --------------------------------------------------------------------------- #
def _normalize(b0: float, b1: float, b2: float, a0: float, a1: float, a2: float) -> Biquad:
    return Biquad(b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def peaking_coefficients(frequency: float, gain_db: float, q: float, sample_rate: int) -> Biquad:
    """RBJ peaking (parametric) EQ — constant 0 dB skirt gain."""
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * frequency / sample_rate
    alpha = math.sin(w0) / (2.0 * q)
    cos_w0 = math.cos(w0)

    b0 = 1.0 + alpha * a
    b1 = -2.0 * cos_w0
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha / a
    return _normalize(b0, b1, b2, a0, a1, a2)


def low_shelf_coefficients(frequency: float, gain_db: float, q: float, sample_rate: int) -> Biquad:
    """RBJ low-shelf EQ (slope ``S`` = 1)."""
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * frequency / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    # With S = 1, alpha = sin(w0)/2 * sqrt(2).
    alpha = sin_w0 / (2.0 * q) * math.sqrt(2.0)
    two_sqrt_a_alpha = 2.0 * math.sqrt(a) * alpha

    b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha)
    b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0)
    b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha
    a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0)
    a2 = (a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha
    return _normalize(b0, b1, b2, a0, a1, a2)


def high_shelf_coefficients(frequency: float, gain_db: float, q: float, sample_rate: int) -> Biquad:
    """RBJ high-shelf EQ (slope ``S`` = 1)."""
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * frequency / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * q) * math.sqrt(2.0)
    two_sqrt_a_alpha = 2.0 * math.sqrt(a) * alpha

    b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha)
    b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0)
    b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha
    a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0)
    a2 = (a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha
    return _normalize(b0, b1, b2, a0, a1, a2)


def lowpass_coefficients(frequency: float, q: float, sample_rate: int) -> Biquad:
    """RBJ low-pass filter."""
    w0 = 2.0 * math.pi * frequency / sample_rate
    alpha = math.sin(w0) / (2.0 * q)
    cos_w0 = math.cos(w0)

    b0 = (1.0 - cos_w0) / 2.0
    b1 = 1.0 - cos_w0
    b2 = (1.0 - cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalize(b0, b1, b2, a0, a1, a2)


def highpass_coefficients(frequency: float, q: float, sample_rate: int) -> Biquad:
    """RBJ high-pass filter."""
    w0 = 2.0 * math.pi * frequency / sample_rate
    alpha = math.sin(w0) / (2.0 * q)
    cos_w0 = math.cos(w0)

    b0 = (1.0 + cos_w0) / 2.0
    b1 = -(1.0 + cos_w0)
    b2 = (1.0 + cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalize(b0, b1, b2, a0, a1, a2)


def bandpass_coefficients(frequency: float, q: float, sample_rate: int) -> Biquad:
    """RBJ band-pass filter (constant 0 dB peak gain)."""
    w0 = 2.0 * math.pi * frequency / sample_rate
    alpha = math.sin(w0) / (2.0 * q)
    cos_w0 = math.cos(w0)

    b0 = alpha
    b1 = 0.0
    b2 = -alpha
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalize(b0, b1, b2, a0, a1, a2)


def notch_coefficients(frequency: float, q: float, sample_rate: int) -> Biquad:
    """RBJ notch (band-stop) filter."""
    w0 = 2.0 * math.pi * frequency / sample_rate
    alpha = math.sin(w0) / (2.0 * q)
    cos_w0 = math.cos(w0)

    b0 = 1.0
    b1 = -2.0 * cos_w0
    b2 = 1.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalize(b0, b1, b2, a0, a1, a2)


def allpass_coefficients(frequency: float, q: float, sample_rate: int) -> Biquad:
    """RBJ all-pass filter."""
    w0 = 2.0 * math.pi * frequency / sample_rate
    alpha = math.sin(w0) / (2.0 * q)
    cos_w0 = math.cos(w0)

    b0 = 1.0 - alpha
    b1 = -2.0 * cos_w0
    b2 = 1.0 + alpha
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha
    return _normalize(b0, b1, b2, a0, a1, a2)


_COEFFICIENT_BUILDERS = {
    "peaking": lambda f, g, q, fs: peaking_coefficients(f, g, q, fs),
    "low_shelf": lambda f, g, q, fs: low_shelf_coefficients(f, g, q, fs),
    "high_shelf": lambda f, g, q, fs: high_shelf_coefficients(f, g, q, fs),
    "lowpass": lambda f, g, q, fs: lowpass_coefficients(f, q, fs),
    "highpass": lambda f, g, q, fs: highpass_coefficients(f, q, fs),
    "bandpass": lambda f, g, q, fs: bandpass_coefficients(f, q, fs),
    "notch": lambda f, g, q, fs: notch_coefficients(f, q, fs),
    "allpass": lambda f, g, q, fs: allpass_coefficients(f, q, fs),
}


def band_coefficients(band: FilterBand, sample_rate: int) -> Biquad:
    """Compute biquad coefficients for a single band."""
    builder = _COEFFICIENT_BUILDERS[band.type]
    return builder(band.frequency, band.gain, band.q, sample_rate)


def log_frequency_axis(f_min: float = 20.0, f_max: float = 20_000.0, points: int = 256) -> List[float]:
    """Return a log-spaced list of frequencies for response plots."""
    if f_min <= 0 or f_max <= f_min or points < 2:
        raise ValueError("invalid frequency axis")
    lo = math.log10(f_min)
    hi = math.log10(f_max)
    return [10.0 ** (lo + (hi - lo) * i / (points - 1)) for i in range(points)]
