"""HID transport and the KTMicro EQ protocol for the Moondrop CHU 2 DSP.

The CHU 2 DSP (a KTMicro KT0210-class chip) is configured through its HID
"Interface 3" (Windows' own driver, :class:`HidTransport`). Playback runs on a
separate UAC1 audio interface, so talking to Interface 3 never breaks sound.

* :func:`kt_read_eq` / :func:`kt_write_eq` — read and write the DSP's EQ
  (KTMicro protocol, see ``docs/PROTOCOL.md`` §2c).

The older pyusb research tools (``DspTransport``, ``probe``, ``test_commands``)
live in :mod:`chu2.research`.
"""

from __future__ import annotations

import math
from typing import Any, List, Sequence, Tuple

from . import device as device_mod, eq

# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
class HidTransport:
    """HID transport for the CHU 2 DSP (interface 3) through Windows' own driver.

    Windows shares Consumer Control collections with apps, so no driver install
    or admin rights are needed (RESEARCH_REPORT.md test #17).
    """

    def __init__(self, hid_device: Any):
        self._dev = hid_device

    @classmethod
    def open(cls) -> "HidTransport":
        hid = device_mod._hidapi()
        dev = hid.device()
        try:
            dev.open(device_mod.MOONDROP_VID, device_mod.CHU2_DSP_PID)
        except Exception as exc:
            raise device_mod.UsbError(
                "Could not open the CHU 2 DSP control channel "
                f"(VID {device_mod.MOONDROP_VID:04X}, PID {device_mod.CHU2_DSP_PID:04X}). "
                "Is it plugged in? Close other EQ tools that may be using it."
            ) from exc
        return cls(dev)

    def write(self, data: bytes) -> int:
        # hidapi expects a list of ints (report id + payload).
        try:
            n = self._dev.write(list(data))
        except (OSError, ValueError) as exc:
            raise device_mod.UsbError(f"CHU 2 write failed: {exc}") from exc
        if n < 0:
            raise device_mod.UsbError(f"CHU 2 write failed (hidapi returned {n})")
        return n

    def read(self, length: int = 64, timeout: int = 1000) -> bytes:
        try:
            return bytes(self._dev.read(length, timeout))
        except (OSError, ValueError) as exc:
            raise device_mod.UsbError(f"CHU 2 read failed: {exc}") from exc

    def product(self) -> str:
        return self._dev.get_product_string()

    def manufacturer(self) -> str:
        return self._dev.get_manufacturer_string()

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:
            pass

    def __enter__(self) -> "HidTransport":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()


def hid_present() -> bool:
    """True when the CHU 2's control channel is plugged in."""
    hid = device_mod._hidapi()
    return bool(hid.enumerate(device_mod.MOONDROP_VID, device_mod.CHU2_DSP_PID))


# --------------------------------------------------------------------------- #
# KTMicro EQ protocol (docs/PROTOCOL.md §2c, from jeromeof/devicePEQ)
# --------------------------------------------------------------------------- #
KT_REPORT_ID = 0x4B
KT_READ, KT_WRITE, KT_COMMIT = 0x52, 0x57, 0x53  # 'R', 'W', 'S'
KT_REG_SLOT = 0x24
KT_REG_BAND0 = 0x26  # band i: gain/freq at 0x26 + 2*i, Q/type at 0x27 + 2*i
KT_SLOT_ON, KT_SLOT_OFF = 0x03, 0x02
KT_BANDS = 5
KT_GAIN_LIMIT_DB = 12.0
KT_FREQ_MIN_HZ = 20.0
KT_FREQ_MAX_HZ = 20_000.0
#: Q range enforced here is the UI range (spec §8 item 3), not the chip's raw
#: 0.1-65 (test #24): whether Q > 10 is audible was never checked.
KT_Q_MIN = 0.1
KT_Q_MAX = 10.0
_KT_TYPES = {"peaking": 0, "low_shelf": 3, "high_shelf": 4}
_KT_TYPE_NAMES = {code: name for name, code in _KT_TYPES.items()}


def kt_packet(reg: int, cmd: int, value: bytes = bytes(4)) -> bytes:
    """10-byte payload: ``[reg][00 00 00][cmd][00][4 value bytes]``."""
    return bytes([reg, 0, 0, 0, cmd, 0]) + value


def kt_encode_band(band: eq.FilterBand) -> Tuple[bytes, bytes]:
    """Return the (gain/freq, Q/type) value bytes for one band."""
    gain_freq = (round(band.gain * 10).to_bytes(2, "little", signed=True)
                 + round(band.frequency).to_bytes(2, "little"))
    q_type = round(band.q * 1000).to_bytes(2, "little") + bytes([_KT_TYPES[band.type], 0])
    return gain_freq, q_type


class UnknownFilterType(device_mod.UsbError):
    """The DSP reports a filter type code this app does not know."""


def kt_decode_band(gain_freq: bytes, q_type: bytes) -> eq.FilterBand:
    if q_type[2] not in _KT_TYPE_NAMES:
        raise UnknownFilterType(f"unknown DSP filter type code {q_type[2]}")
    return eq.FilterBand(
        type=_KT_TYPE_NAMES[q_type[2]],
        frequency=float(int.from_bytes(gain_freq[2:4], "little")),
        gain=int.from_bytes(gain_freq[0:2], "little", signed=True) / 10,
        q=int.from_bytes(q_type[0:2], "little") / 1000,
    )


def kt_fit_bands(bands: Sequence[eq.FilterBand]) -> List[eq.FilterBand]:
    """Fit bands to the DSP: at most 5, peaking/shelves only, within ±12 dB,
    with a finite frequency in 20-20000 Hz and a Q in 0.1-10.

    Missing bands are filled with flat (0 dB) peaking bands.
    """
    if len(bands) > KT_BANDS:
        raise ValueError(
            f"the CHU 2 DSP has {KT_BANDS} bands; this preset has {len(bands)}"
        )
    for i, band in enumerate(bands, start=1):
        if band.type not in _KT_TYPES:
            raise ValueError(
                f"band {i}: type {band.type!r} is not supported by the DSP "
                f"(use {', '.join(_KT_TYPES)})"
            )
        if not (math.isfinite(band.frequency) and math.isfinite(band.gain)
                and math.isfinite(band.q)):
            raise ValueError(
                f"band {i}: frequency, gain and Q must be finite numbers "
                f"(got frequency={band.frequency}, gain={band.gain}, q={band.q})"
            )
        if abs(band.gain) > KT_GAIN_LIMIT_DB:
            raise ValueError(f"band {i}: gain {band.gain} dB is outside ±12 dB")
        if not (KT_FREQ_MIN_HZ <= band.frequency <= KT_FREQ_MAX_HZ):
            raise ValueError(
                f"band {i}: frequency {band.frequency} Hz is outside "
                f"{KT_FREQ_MIN_HZ:.0f}-{KT_FREQ_MAX_HZ:.0f} Hz"
            )
        if not (KT_Q_MIN <= band.q <= KT_Q_MAX):
            raise ValueError(f"band {i}: Q {band.q} is outside {KT_Q_MIN}-{KT_Q_MAX}")
    flat = eq.FilterBand(type="peaking", frequency=1000.0, gain=0.0, q=1.0)
    return list(bands) + [flat] * (KT_BANDS - len(bands))


def kt_command(transport: Any, payload: bytes) -> bytes:
    """Send one command and return the 4 value bytes of its reply.

    ``transport`` needs ``write(report) -> int`` and
    ``read(length, timeout_ms) -> bytes``, returning ``b""`` on timeout
    (:class:`HidTransport` and ``chu2.fake_device.FakeChu2``).
    """
    transport.write(bytes([KT_REPORT_ID]) + payload)
    for _ in range(5):  # skip unrelated input reports
        reply = transport.read(64, 500)
        if not reply:
            break
        if (len(reply) >= 11 and reply[0] == KT_REPORT_ID
                and reply[1] == payload[0] and reply[5] == payload[4]):
            return bytes(reply[7:11])
    raise device_mod.UsbError(f"no reply from the DSP to {payload.hex(' ')}")


def kt_read_eq(transport: Any) -> Tuple[int, List[eq.FilterBand]]:
    """Return (EQ slot, bands) as the DSP plays them now."""
    slot = kt_command(transport, kt_packet(KT_REG_SLOT, KT_READ, bytes([KT_SLOT_ON, 0, 0, 0])))[0]
    bands = []
    for i in range(KT_BANDS):
        reg = KT_REG_BAND0 + 2 * i
        bands.append(kt_decode_band(kt_command(transport, kt_packet(reg, KT_READ)),
                                    kt_command(transport, kt_packet(reg + 1, KT_READ))))
    return slot, bands


def kt_write_band(transport: Any, index: int, band: eq.FilterBand) -> Tuple[bytes, bytes]:
    """Play ``band`` on slot ``index`` now (no commit); return the bytes written."""
    reg = KT_REG_BAND0 + 2 * index
    values = kt_encode_band(band)
    for r, value in zip((reg, reg + 1), values):
        kt_command(transport, kt_packet(r, KT_WRITE, value))
    return values


def kt_verify_band(transport: Any, index: int, values: Tuple[bytes, bytes]) -> bool:
    reg = KT_REG_BAND0 + 2 * index
    return all(kt_command(transport, kt_packet(r, KT_READ)) == value
               for r, value in zip((reg, reg + 1), values))


def kt_set_slot(transport: Any, slot: int) -> None:
    """Select the EQ slot (0x03 custom/on, 0x02 off) without commit."""
    kt_command(transport, kt_packet(KT_REG_SLOT, KT_WRITE, bytes([slot, 0, 0, 0])))


def kt_commit(transport: Any) -> None:
    """Save what the DSP plays now. The CHU 2 then drops off USB and restarts."""
    kt_command(transport, kt_packet(0x00, KT_COMMIT))


def kt_write_eq(transport: Any, bands: Sequence[eq.FilterBand],
                commit: bool = True) -> None:
    """Write bands, verify each by read-back, then commit (save).

    A read-back mismatch raises before the commit, so a wrong EQ is never saved.
    """
    bands = kt_fit_bands(bands)
    slot = kt_command(transport, kt_packet(KT_REG_SLOT, KT_READ, bytes([KT_SLOT_ON, 0, 0, 0])))[0]
    if slot == KT_SLOT_OFF:
        kt_set_slot(transport, KT_SLOT_ON)
    for i, band in enumerate(bands):
        if not kt_verify_band(transport, i, kt_write_band(transport, i, band)):
            raise device_mod.UsbError(
                f"band {i + 1}: read-back does not match the write; nothing saved"
            )
    if commit:
        kt_commit(transport)
