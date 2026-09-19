"""Preset management for the Moondrop CHU 2 DSP.

A preset is a JSON document describing an ordered set of EQ bands. It is the
portable unit that can be:

* loaded/saved/validated offline,
* exported to EqualizerAPO (for system-wide EQ) or plain coefficients,
* and, once the DSP protocol is known, applied to the device.
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Any, Dict, List, Optional

from . import eq

#: JSON schema version. Bumped when the format changes incompatibly.
SCHEMA_VERSION: int = 1

#: Valid gain range (dB). Matches common ±12 dB parametric-EQ limits.
GAIN_MIN_DB: float = -12.0
GAIN_MAX_DB: float = 12.0

#: Sensible frequency/Q bounds used for validation.
FREQUENCY_MIN_HZ: float = 20.0
FREQUENCY_MAX_HZ: float = 20_000.0
Q_MIN: float = 0.1
Q_MAX: float = 20.0


class PresetError(ValueError):
    """Raised when a preset file or structure is invalid."""


@dataclasses.dataclass
class Preset:
    """A named, ordered EQ preset."""

    name: str
    bands: List[eq.FilterBand]
    description: str = ""
    sample_rate: int = eq.DEFAULT_SAMPLE_RATE
    version: int = SCHEMA_VERSION
    preamp: float = 0.0  # dB, applied as a flat gain offset (usually <= 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "description": self.description,
            "sample_rate": self.sample_rate,
            "preamp": self.preamp,
            "bands": [
                {
                    "type": band.type,
                    "frequency": band.frequency,
                    "gain": band.gain,
                    "q": band.q,
                }
                for band in self.bands
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False) + "\n"

    def equalizer(self) -> eq.Equalizer:
        return eq.Equalizer(bands=self.bands, sample_rate=self.sample_rate)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate(data: Any) -> List[str]:
    """Validate a preset dict, returning a list of human-readable problems."""
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["preset must be a JSON object"]

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("'name' must be a non-empty string")

    sample_rate = data.get("sample_rate", eq.DEFAULT_SAMPLE_RATE)
    if not isinstance(sample_rate, (int, float)) or sample_rate <= 0:
        errors.append("'sample_rate' must be a positive number")

    bands = data.get("bands")
    if not isinstance(bands, list) or not bands:
        errors.append("'bands' must be a non-empty list")
        return errors

    for i, band in enumerate(bands):
        if not isinstance(band, dict):
            errors.append(f"bands[{i}] must be an object")
            continue
        ftype = band.get("type", "peaking")
        if ftype not in eq.FILTER_TYPES:
            errors.append(
                f"bands[{i}].type {ftype!r} is invalid (expected one of {eq.FILTER_TYPES})"
            )
        for key, low, high, label in (
            ("frequency", FREQUENCY_MIN_HZ, FREQUENCY_MAX_HZ, "Hz"),
            ("gain", GAIN_MIN_DB, GAIN_MAX_DB, "dB"),
            ("q", Q_MIN, Q_MAX, ""),
        ):
            value = band.get(key)
            if not isinstance(value, (int, float)):
                errors.append(f"bands[{i}].{key} must be a number")
            elif not (low <= value <= high):
                errors.append(
                    f"bands[{i}].{key}={value} is out of range [{low}, {high}]{label}"
                )
    return errors


def preset_from_dict(data: Any) -> Preset:
    """Build a :class:`Preset` from a dict, raising on validation failure."""
    errors = validate(data)
    if errors:
        raise PresetError("Invalid preset:\n  " + "\n  ".join(errors))

    bands = [
        eq.FilterBand(
            type=band.get("type", "peaking"),
            frequency=float(band.get("frequency", 1000.0)),
            gain=float(band.get("gain", 0.0)),
            q=float(band.get("q", 1.0)),
        )
        for band in data["bands"]
    ]
    return Preset(
        name=str(data.get("name", "Untitled")).strip(),
        description=str(data.get("description", "")),
        sample_rate=int(data.get("sample_rate", eq.DEFAULT_SAMPLE_RATE)),
        version=int(data.get("version", SCHEMA_VERSION)),
        preamp=float(data.get("preamp", 0.0)),
        bands=bands,
    )


# --------------------------------------------------------------------------- #
# Load / save
# --------------------------------------------------------------------------- #
def load(path: str) -> Preset:
    """Load and validate a preset from a JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise PresetError(f"preset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PresetError(f"invalid JSON in {path}: {exc}") from exc
    return preset_from_dict(data)


def save(preset: Preset, path: str) -> None:
    """Write a preset to a JSON file (creating parent directories)."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(preset.to_json())


def discover(directory: str) -> List[str]:
    """Return the JSON preset files found under ``directory`` (sorted)."""
    if not os.path.isdir(directory):
        return []
    found: List[str] = []
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if name.lower().endswith(".json"):
                found.append(os.path.join(root, name))
    return sorted(found)


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def to_equalizer_apo(preset: Preset) -> str:
    """Render a preset as an EqualizerAPO config (parametric filters)."""
    lines: List[str] = [
        f"# {preset.name}",
        f"# Exported by chu2-dsp (sample rate {preset.sample_rate} Hz)",
    ]
    if preset.description:
        lines.append(f"# {preset.description}")
    lines.append(f"Preamp: {preset.preamp:.1f} dB")
    for band in preset.bands:
        code = eq.EQUALIZER_APO_CODES[band.type]
        if band.type in ("peaking", "low_shelf", "high_shelf"):
            lines.append(
                f"Filter: ON {code} Fc {band.frequency:.1f} Hz "
                f"Gain {band.gain:.1f} dB Q {band.q:.3f}"
            )
        else:
            lines.append(f"Filter: ON {code} Fc {band.frequency:.1f} Hz Q {band.q:.3f}")
    return "\n".join(lines) + "\n"


def to_coefficients_csv(preset: Preset) -> str:
    """Render biquad coefficients as CSV for verification or DSP upload."""
    lines = ["type,frequency,gain,q,b0,b1,b2,a1,a2"]
    for band, biquad in zip(preset.bands, preset.equalizer().coefficients()):
        lines.append(
            f"{band.type},{band.frequency:.2f},{band.gain:.2f},{band.q:.3f},"
            f"{biquad.b0:.10f},{biquad.b1:.10f},{biquad.b2:.10f},"
            f"{biquad.a1:.10f},{biquad.a2:.10f}"
        )
    return "\n".join(lines) + "\n"


#: Reverse map: EqualizerAPO filter code -> our band type.
_APO_TO_TYPE = {
    "PK": "peaking", "LSC": "low_shelf", "HSC": "high_shelf",
    "LP": "lowpass", "HP": "highpass", "BP": "bandpass", "NO": "notch",
    "AP": "allpass", "LS": "low_shelf", "HS": "high_shelf",
}


def from_equalizer_apo(text: str, name: str = "Imported") -> Preset:
    """Parse an EqualizerAPO/Peace config into a :class:`Preset`.

    Handles both ``Filter: ON ...`` and Peace's ``Filter 1: ON ...`` forms, and
    maps ``Preamp:`` to the preset's preamp. Returns an empty preset if no
    filters are found.
    """
    import re as _re

    bands: List[eq.FilterBand] = []
    preamp = 0.0
    for line in text.splitlines():
        cleaned = _re.sub(r"#.*", "", line).strip()
        if not cleaned:
            continue

        m = _re.match(r"Preamp:\s*([+-]?[\d.]+)\s*dB", cleaned, _re.IGNORECASE)
        if m:
            preamp = float(m.group(1))
            continue

        m = _re.match(
            r"Filter\s*\d*:\s*(?:ON|1)\s+(\w+)\s+Fc\s+([\d.]+)\s*Hz"
            r"(?:\s+Gain\s+([+-]?[\d.]+)\s*dB)?(?:\s+Q\s+([\d.]+))?",
            cleaned, _re.IGNORECASE,
        )
        if m:
            code = m.group(1).upper()
            ftype = _APO_TO_TYPE.get(code, "peaking")
            freq = float(m.group(2))
            gain = float(m.group(3)) if m.group(3) is not None else 0.0
            q = float(m.group(4)) if m.group(4) is not None else 1.0
            bands.append(eq.FilterBand(type=ftype, frequency=freq, gain=gain, q=q))

    return Preset(name=name, bands=bands, preamp=preamp)


def flat_preset(name: str = "Default (Flat)") -> Preset:
    """Return a neutral example preset used as the tool's default template."""
    return Preset(
        name=name,
        description="Neutral template. Adjust and re-save as your own preset.",
        sample_rate=eq.DEFAULT_SAMPLE_RATE,
        bands=[
            eq.FilterBand(type="peaking", frequency=100.0, gain=0.0, q=1.0),
            eq.FilterBand(type="peaking", frequency=300.0, gain=0.0, q=1.0),
            eq.FilterBand(type="peaking", frequency=1000.0, gain=0.0, q=1.0),
            eq.FilterBand(type="peaking", frequency=3000.0, gain=0.0, q=1.0),
            eq.FilterBand(type="peaking", frequency=8000.0, gain=0.0, q=1.0),
        ],
    )
