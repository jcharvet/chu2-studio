"""Import and export (brief S7).

Reads pasted or opened text of three kinds and returns a preview the page
shows before anything changes:

* a share code (``CHU2-1.…``, :mod:`chu2.sharecode`), anywhere in the text;
* a CHU 2 Studio preset (``.chu2.json``, the :mod:`chu2.preset` format);
* Equalizer APO / AutoEq ``ParametricEQ.txt`` / Peace text (``Filter …: ON PK
  Fc … Hz Gain … dB Q …`` lines and an optional ``Preamp:`` line);
* the app's own "Copy as text" line (``PK 166 Hz −2.6 Q0.87 · …``,
  :func:`chu2.sharecode.describe`).

The CHU 2 has five bands of peak / low shelf / high shelf: other filter types
are listed but not used, values are clamped to the CHU 2's limits, and when a
file has more than five filters the five with the largest gain are kept (in
file order). The file's preamp is shown, not copied: the app builds its own
preamp from the bands (spec §4.4).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence

from . import dsp, eq, preamp, quicktune, sharecode

_TYPES = {"PK": "peaking", "PEQ": "peaking", "LS": "low_shelf", "LSC": "low_shelf",
          "LSQ": "low_shelf", "HS": "high_shelf", "HSC": "high_shelf", "HSQ": "high_shelf"}
_CODES = {"peaking": "PK", "low_shelf": "LSC", "high_shelf": "HSC"}
_OTHER = {"HP": "high-pass", "HPQ": "high-pass", "LP": "low-pass", "LPQ": "low-pass",
          "BP": "band-pass", "NO": "notch", "AP": "all-pass"}
_FILTER = re.compile(
    r"^Filter\s*\d*\s*:\s*(ON|OFF)\s+([A-Za-z]+)(?:\s+\d+\s*dB)?\s+Fc\s+([\d.]+)\s*Hz"
    r"(?:\s+Gain\s+([+-]?[\d.]+)\s*dB)?(?:\s+Q\s+([\d.]+))?", re.IGNORECASE)
_PREAMP = re.compile(r"^Preamp\s*:\s*([+-]?[\d.]+)\s*dB", re.IGNORECASE)
_TEXT_BAND = re.compile(r"\b(PK|LS|HS)\s+([\d.]+)\s*(k?)Hz\s+([+\-−][\d.]+)\s+Q\s*([\d.]+)")


class TransferError(ValueError):
    """Nothing the CHU 2 can use in this text or file."""


def _minus(value: float) -> str:
    return ("−" if value < 0 else "+" if value > 0 else "") + f"{abs(value):.1f}"


def _row(n: int, kind: Optional[str], code: str, frequency: float, gain: float,
         q: Optional[float], bypass: bool = False) -> Dict[str, Any]:
    """One filter of the file, clamped to the CHU 2 and given a plain status."""
    if kind is None:
        name = _OTHER.get(code.upper(), f"'{code}' filter")
        return {"n": n, "code": code.upper(), "type": None, "frequency": frequency, "gain": gain,
                "q": q, "status": f"{name} isn't available on CHU 2"}
    q = q if q is not None else (1.0 if kind == "peaking" else 0.71)
    status = "fits"
    clamped_gain = min(max(gain, -dsp.KT_GAIN_LIMIT_DB), dsp.KT_GAIN_LIMIT_DB)
    clamped_freq = min(max(frequency, dsp.KT_FREQ_MIN_HZ), dsp.KT_FREQ_MAX_HZ)
    clamped_q = min(max(q, dsp.KT_Q_MIN), dsp.KT_Q_MAX)
    if clamped_gain != gain:
        status = f"gain limited to {'+' if clamped_gain > 0 else chr(0x2212)}{abs(clamped_gain):.1f}"
    elif clamped_freq != frequency:
        status = f"frequency limited to {clamped_freq:.0f} Hz"
    elif clamped_q != q:
        status = f"Q limited to {clamped_q:g}"
    return {"n": n, "code": code.upper(), "type": kind, "frequency": float(round(clamped_freq)),
            "gain": round(clamped_gain, 1) + 0.0, "q": round(clamped_q, 3), "bypass": bypass,
            "status": status}


def _preview(name: str, fmt: str, rows: List[Dict[str, Any]],
             file_preamp: Optional[float]) -> Dict[str, Any]:
    usable = [r for r in rows if r["type"] is not None]
    if not usable:
        raise TransferError("No EQ filters the CHU 2 can play were found in this text.")
    largest = sorted(usable, key=lambda r: (-abs(r["gain"]), r["n"]))[:dsp.KT_BANDS]
    kept = sorted(largest, key=lambda r: r["n"])
    kept_n = {r["n"] for r in kept}
    for row in usable:
        if row["n"] not in kept_n:
            row["status"] = "not kept (5 bands)"
    bands = [{"type": r["type"], "frequency": r["frequency"], "gain": r["gain"], "q": r["q"],
              "bypass": r.get("bypass", False)} for r in kept]
    bands += [dict(b) for b in quicktune.IDLE_DESIGN[len(bands):]]
    notes = []
    if len(usable) > dsp.KT_BANDS:
        notes.append(f"CHU 2 has 5 bands. This file has {len(rows)}: keeping the 5 largest.")
    if file_preamp:
        notes.append(f"The file's preamp ({_minus(file_preamp)} dB) isn't copied: CHU 2 Studio works out "
                     "its own preamp from the bands.")
    heard = [eq.FilterBand(b["type"], b["frequency"], 0.0 if b["bypass"] else b["gain"], b["q"])
             for b in bands]
    return {"name": name, "format": fmt, "filters": rows, "total": len(rows), "bands": bands,
            "preamp": file_preamp, "peak_db": round(preamp.peak(heard)[0], 1) + 0.0, "notes": notes}


def read_text(text: str, source_name: str = "") -> Dict[str, Any]:
    """A preview of pasted or opened text; raises :class:`TransferError`."""
    stem = os.path.basename(source_name)
    for ending in (".chu2.json", ".json", ".txt"):
        if stem.lower().endswith(ending):
            stem = stem[: -len(ending)]
            break
    code = sharecode.find_code(text)
    if code:
        try:
            name, bands = sharecode.decode(code)
        except sharecode.ShareCodeError as exc:
            raise TransferError(str(exc)) from exc
        rows = [_row(i + 1, b.type, _CODES[b.type], b.frequency, b.gain, b.q)
                for i, b in enumerate(bands)]
        return _preview(name, "Share code", rows, None)
    if text.lstrip().startswith("{"):
        try:
            data = json.loads(text)
            rows = [_row(i + 1, b.get("type") if b.get("type") in _CODES else None,
                         _CODES.get(b.get("type"), str(b.get("type"))), float(b["frequency"]),
                         float(b.get("gain", 0.0)), float(b.get("q", 1.0)), bool(b.get("bypass", False)))
                    for i, b in enumerate(data["bands"])]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise TransferError("This preset file can't be read.") from exc
        return _preview(str(data.get("name") or stem or "Imported"), "CHU 2 Studio preset", rows, None)
    rows, file_preamp = [], None
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        match = _PREAMP.match(line)
        if match:
            try:
                file_preamp = float(match.group(1))
            except ValueError:
                pass  # a garbled number ("-.."): ignore the line
            continue
        match = _FILTER.match(line)
        if not match or match.group(1).upper() == "OFF":
            continue  # a filter switched off is not heard
        code = match.group(2)
        try:
            frequency = float(match.group(3))
            gain = float(match.group(4)) if match.group(4) else 0.0
            q = float(match.group(5)) if match.group(5) else None
        except ValueError:
            continue  # a garbled number ("1..2"): skip the line
        rows.append(_row(len(rows) + 1, _TYPES.get(code.upper()), code, frequency, gain, q))
    if not rows:  # the app's own "Copy as text" line
        for match in _TEXT_BAND.finditer(text):
            try:
                frequency = float(match.group(2)) * (1000 if match.group(3) else 1)
                gain = float(match.group(4).replace("−", "-"))
                q = float(match.group(5))
            except ValueError:
                continue  # a garbled number: skip the band
            rows.append(_row(len(rows) + 1, _TYPES[match.group(1)], match.group(1), frequency, gain, q))
        if rows:
            return _preview(stem or "Imported", "CHU 2 Studio text", rows, None)
    if not rows:
        raise TransferError("No EQ filters were found. Paste a share code, or an Equalizer APO / "
                            "AutoEq / Peace text.")
    return _preview(stem or "Imported", "Equalizer APO / AutoEq text", rows, file_preamp)


def preset_document(name: str, design: Sequence[Dict[str, Any]], tags: Sequence[str] = ()) -> Dict[str, Any]:
    """A ``.chu2.json`` document (the chu2.preset format plus tags and bypass)."""
    return {"version": 1, "name": name, "description": "", "sample_rate": 48000, "preamp": 0.0,
            "tags": [str(t) for t in tags], "bands": [dict(b) for b in design]}


def export_json(name: str, design: Sequence[Dict[str, Any]], tags: Sequence[str] = ()) -> str:
    return json.dumps(preset_document(name, design, tags), indent=2) + "\n"


def export_apo(name: str, design: Sequence[Dict[str, Any]], preamp_db: float) -> str:
    """Equalizer APO / AutoEq text, with the app's preamp as the ``Preamp:`` line."""
    lines = [f"# {name}", "# Exported from CHU 2 Studio. On the CHU 2 the preamp is built into the bands.",
             f"Preamp: {preamp_db + 0.0:.1f} dB"]
    for i, band in enumerate(design, start=1):
        state = "OFF" if band.get("bypass") else "ON"
        lines.append(f"Filter {i}: {state} {_CODES[band['type']]} Fc {band['frequency']:.0f} Hz "
                     f"Gain {band['gain']:.1f} dB Q {band['q']:.3f}")
    return "\n".join(lines) + "\n"
