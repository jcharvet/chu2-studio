"""The packaged fake CHU 2 and its plug (no device needed).

    python -m pytest -q tests/test_fake_device.py
"""

from chu2 import device as device_mod, dsp, eq
from chu2.fake_device import FakeChu2, FakePlug

BASS = eq.FilterBand("low_shelf", 100.0, 6.0, 0.7)


def _raises_usb_error(func) -> bool:
    try:
        func()
    except device_mod.UsbError:
        return True
    return False


def test_pulled_plug_cannot_be_opened():
    plug = FakePlug(present=False)
    assert not plug.is_present()
    assert _raises_usb_error(plug.open)


def test_commit_drops_off_usb_then_returns_with_the_saved_eq():
    plug = FakePlug(restart_polls=2)
    fake = plug.open()
    dsp.kt_write_band(fake, 0, BASS)
    dsp.kt_commit(fake)
    assert [plug.is_present(), plug.is_present(), plug.is_present()] == [False, False, True]
    fake = plug.open()
    assert dsp.kt_read_eq(fake)[1][0] == BASS


def test_a_restart_forgets_unsaved_live_writes():
    plug = FakePlug()
    fake = plug.open()
    dsp.kt_commit(fake)            # saves the EQ as it is now
    dsp.kt_write_band(fake, 0, BASS)  # live only
    plug.is_present()              # the restart after the commit
    assert dsp.kt_read_eq(plug.open())[1][0].gain == -1.5


def test_closed_fake_refuses_io_until_reopened():
    plug = FakePlug()
    fake = plug.open()
    fake.close()
    assert _raises_usb_error(lambda: dsp.kt_read_eq(fake))
    assert dsp.kt_read_eq(plug.open())[0] == dsp.KT_SLOT_ON


def test_fake_is_a_context_manager():
    with FakeChu2() as fake:
        assert dsp.kt_read_eq(fake)[0] == dsp.KT_SLOT_ON
    assert fake.closed
