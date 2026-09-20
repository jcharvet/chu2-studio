"""Protocol I/O against a fake CHU 2 (no device needed).

    python -m pytest -q tests/test_dsp_io.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chu2 import device as device_mod, dsp, eq  # noqa: E402
from chu2.fake_device import FakeChu2  # noqa: E402

BASS = eq.FilterBand("low_shelf", 100.0, 6.0, 0.7)


def test_read_eq_decodes_our_unit():
    slot, bands = dsp.kt_read_eq(FakeChu2())
    assert slot == dsp.KT_SLOT_ON
    assert [(b.type, b.frequency, b.gain, b.q) for b in bands] == [
        ("peaking", 40.0, -1.5, 0.5),
        ("peaking", 200.0, -6.0, 0.6),
        ("peaking", 1400.0, -2.5, 1.6),
        ("peaking", 3500.0, -4.8, 1.0),
        ("peaking", 9000.0, -2.0, 1.5),
    ]


def test_write_band_is_live_and_not_committed():
    fake = FakeChu2()
    dsp.kt_write_band(fake, 1, BASS)
    assert fake.live[0x28] == bytes.fromhex("3c006400")  # +6.0 dB, 100 Hz
    assert fake.live[0x29] == bytes.fromhex("bc020300")  # Q 0.700, low shelf
    assert fake.commits == 0


def test_write_eq_pads_verifies_and_commits():
    fake = FakeChu2()
    dsp.kt_write_eq(fake, [BASS])
    assert fake.commits == 1
    _slot, bands = dsp.kt_read_eq(fake)
    assert bands[0] == BASS
    assert all(b.gain == 0 for b in bands[1:])


def test_write_eq_mismatch_is_never_committed():
    fake = FakeChu2()
    fake.ignore_writes_to = {0x26}
    try:
        dsp.kt_write_eq(fake, [BASS])
    except device_mod.UsbError:
        pass
    else:
        raise AssertionError("read-back mismatch was not detected")
    assert fake.commits == 0


def test_set_slot_writes_register_0x24_without_commit():
    fake = FakeChu2()
    dsp.kt_set_slot(fake, dsp.KT_SLOT_OFF)
    assert fake.live[0x24][0] == dsp.KT_SLOT_OFF and fake.commits == 0


class _DropsFirstReply(FakeChu2):
    """A CHU 2 that loses the very first reply, as a busy USB bus sometimes does."""

    def read(self, length: int = 64, timeout: int = 1000) -> bytes:
        reply = super().read(length, timeout)
        if not getattr(self, "_dropped", False):
            self._dropped = True
            return b""
        return reply


def test_one_lost_reply_is_retried_not_an_error():
    fake = _DropsFirstReply()
    slot, bands = dsp.kt_read_eq(fake)
    assert slot == dsp.KT_SLOT_ON
    assert bands[1].gain == -6.0


def test_silent_device_raises_usb_error():
    fake = FakeChu2()
    fake.silent = True
    try:
        dsp.kt_command(fake, dsp.kt_packet(dsp.KT_REG_SLOT, dsp.KT_READ))
    except device_mod.UsbError:
        return
    raise AssertionError("no error from a silent device")


# ---- Important 1: HidTransport turns low-level failures into UsbError ---- #
class _RawHidDevice:
    """Stand-in for the object hidapi's ``hid.device()`` returns."""

    def __init__(self, write_effect=None, read_effect=None, write_return=None):
        self._write_effect = write_effect
        self._read_effect = read_effect
        self._write_return = write_return

    def write(self, data):
        if self._write_effect is not None:
            raise self._write_effect
        return len(data) if self._write_return is None else self._write_return

    def read(self, length, timeout):
        if self._read_effect is not None:
            raise self._read_effect
        return []


def test_hid_transport_write_turns_os_error_into_usb_error():
    transport = dsp.HidTransport(_RawHidDevice(write_effect=OSError("device removed")))
    try:
        transport.write(b"\x4b\x00")
    except device_mod.UsbError:
        return
    raise AssertionError("OSError from hidapi write() did not become UsbError")


def test_hid_transport_write_turns_value_error_into_usb_error():
    transport = dsp.HidTransport(_RawHidDevice(write_effect=ValueError("bad report")))
    try:
        transport.write(b"\x4b\x00")
    except device_mod.UsbError:
        return
    raise AssertionError("ValueError from hidapi write() did not become UsbError")


def test_hid_transport_write_negative_return_is_usb_error():
    transport = dsp.HidTransport(_RawHidDevice(write_return=-1))
    try:
        transport.write(b"\x4b\x00")
    except device_mod.UsbError:
        return
    raise AssertionError("a negative hidapi write() result did not raise UsbError")


def test_hid_transport_read_turns_os_error_into_usb_error():
    transport = dsp.HidTransport(_RawHidDevice(read_effect=OSError("device removed")))
    try:
        transport.read(64, 100)
    except device_mod.UsbError:
        return
    raise AssertionError("OSError from hidapi read() did not become UsbError")


def test_hid_transport_read_turns_value_error_into_usb_error():
    transport = dsp.HidTransport(_RawHidDevice(read_effect=ValueError("bad length")))
    try:
        transport.read(64, 100)
    except device_mod.UsbError:
        return
    raise AssertionError("ValueError from hidapi read() did not become UsbError")
