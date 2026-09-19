"""Share codes (brief S7): a whole five-band EQ in one short line of text.

    CHU2-1.<name>.<payload>.<CRC-16>

``name`` is url-safe (letters, digits, ``_`` and ``-``). ``payload`` is
base64url without padding of the five bands packed MSB-first, 41 bits each:
type (2 bits: 0 peak, 1 low shelf, 2 high shelf), frequency (15 bits, Hz),
gain (8 bits two's complement, 0.1 dB) and Q (16 bits, x1000) — exactly the
steps the CHU 2 stores. The last part is CRC-16/CCITT-FALSE of everything
before the last dot, as 4 hex digits, so a typo is caught. No server needed.
"""

from __future__ import annotations

import base64
import re
from typing import List, Optional, Sequence, Tuple

from . import dsp, eq

VERSION = 1
PREFIX = "CHU2"
TYPES = ("peaking", "low_shelf", "high_shelf")
_CODES = {"peaking": "PK", "low_shelf": "LS", "high_shelf": "HS"}
_BITS = 41
_FIND = re.compile(r"CHU2-\d{1,4}\.[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[0-9A-Fa-f]{4}")


class ShareCodeError(ValueError):
    """Not a share code, a typo, or a code from a newer app."""


def crc16(text: str) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in text.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def safe_name(name: str) -> str:
    """"Night Drive!" -> "NightDrive": words joined, first letters capitalised."""
    words = re.findall(r"[A-Za-z0-9_-]+", name)
    joined = "".join(w[:1].upper() + w[1:] for w in words)[:32]
    return joined or "EQ"


def encode(name: str, bands: Sequence[eq.FilterBand]) -> str:
    """The share code for ``bands`` (up to 5; missing bands are flat)."""
    value = 0
    for band in dsp.kt_fit_bands(bands):
        gain = round(band.gain * 10) & 0xFF
        value = (value << _BITS) | (TYPES.index(band.type) << 39) | (round(band.frequency) << 24) \
            | (gain << 16) | round(band.q * 1000)
    bits = _BITS * dsp.KT_BANDS
    raw = (value << (8 - bits % 8)).to_bytes((bits + 7) // 8, "big")
    payload = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    head = f"{PREFIX}-{VERSION}.{safe_name(name)}.{payload}"
    return f"{head}.{crc16(head):04X}"


def decode(code: str) -> Tuple[str, List[eq.FilterBand]]:
    """(name, 5 bands) from a share code; spaces and line breaks are ignored."""
    code = re.sub(r"\s+", "", code)
    parts = code.split(".")
    if len(parts) != 4 or not re.fullmatch(r"CHU2-\d{1,4}", parts[0]):  # int() refuses huge ones
        raise ShareCodeError("This is not a CHU 2 Studio share code.")
    version = int(parts[0].split("-")[1])
    if version != VERSION:
        raise ShareCodeError("This code was made by a newer CHU 2 Studio. Please update the app.")
    head, check = code.rsplit(".", 1)
    if f"{crc16(head):04X}" != check.upper():
        raise ShareCodeError("The check digits don't match: part of the code is missing or mistyped.")
    try:
        raw = base64.urlsafe_b64decode(parts[2] + "=" * (-len(parts[2]) % 4))
    except ValueError as exc:
        raise ShareCodeError("The code's EQ part can't be read.") from exc
    bits = _BITS * dsp.KT_BANDS
    if len(raw) != (bits + 7) // 8:
        raise ShareCodeError("The code's EQ part has the wrong length.")
    value = int.from_bytes(raw, "big") >> (8 - bits % 8)
    bands = []
    for i in reversed(range(dsp.KT_BANDS)):
        chunk = (value >> (_BITS * i)) & ((1 << _BITS) - 1)
        kind = chunk >> 39
        if kind >= len(TYPES):
            raise ShareCodeError("The code has a filter type this app doesn't know.")
        gain = (chunk >> 16) & 0xFF
        gain = gain - 256 if gain > 127 else gain
        bands.append(eq.FilterBand(TYPES[kind], float((chunk >> 24) & 0x7FFF), gain / 10,
                                   (chunk & 0xFFFF) / 1000))
    try:
        dsp.kt_fit_bands(bands)
    except ValueError as exc:
        raise ShareCodeError(f"The code has a value the CHU 2 can't store: {exc}") from exc
    return parts[1], bands


def find_code(text: str) -> Optional[str]:
    """The first share code in pasted text (which may be wrapped), or None."""
    match = _FIND.search(re.sub(r"\s+", "", text))
    return match.group(0) if match else None


def describe(bands: Sequence[eq.FilterBand]) -> str:
    """Plain text for a message: "LS 80 Hz +3.5 Q0.71 · PK 250 Hz −2.0 Q1.00"."""
    parts = []
    for band in bands:
        if band.gain == 0:
            continue
        freq = (f"{band.frequency / 1000:.2f}".rstrip("0").rstrip(".") + " kHz"
                if band.frequency >= 1000 else f"{band.frequency:.0f} Hz")
        sign = "+" if band.gain > 0 else "−"
        parts.append(f"{_CODES[band.type]} {freq} {sign}{abs(band.gain):.1f} Q{band.q:.2f}")
    return " · ".join(parts) if parts else "Flat (all bands at 0 dB)"
