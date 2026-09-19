"""DeviceService against a fake CHU 2 (no device needed).

    python -m pytest -q tests/test_device_service.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chu2 import device as device_mod, dsp, eq  # noqa: E402
from chu2.device_service import DeviceService  # noqa: E402
from chu2.fake_device import FakeChu2, FakePlug  # noqa: E402

BASS = eq.FilterBand("low_shelf", 100.0, 6.0, 0.7)
LESS_BASS = eq.FilterBand("low_shelf", 100.0, 2.0, 0.7)


def _live_worker_threads():
    return [t for t in threading.enumerate() if t.name == "chu2-device" and t.is_alive()]


class Harness:
    """A FakePlug around a FakeChu2, plus the events the service sent."""

    def __init__(self, sleep=lambda s: None, poll_s=1.0):
        self.plug = FakePlug()
        self.fake = self.plug.device
        self.events = []
        self.svc = DeviceService(self.plug.open, self.plug.is_present, self.on_event,
                                 sleep=sleep, restart_timeout_s=0.5, poll_s=poll_s)

    @property
    def present(self):
        return self.plug.present

    @present.setter
    def present(self, value):
        self.plug.present = value

    def on_event(self, name, data):
        self.events.append((name, data))

    def names(self):
        return [name for name, _ in self.events]


def test_connect_reads_the_eq():
    h = Harness()
    h.svc.run_once(now=0)
    name, data = h.events[-1]
    assert name == "connected" and data["slot"] == dsp.KT_SLOT_ON
    assert data["bands"][1].gain == -6.0
    assert h.svc.connected


def test_live_edits_are_coalesced_and_not_committed():
    h = Harness()
    h.svc.run_once(now=0)
    h.svc.set_band_live(0, BASS)
    h.svc.set_band_live(0, LESS_BASS)  # only the last value is sent
    h.svc.run_once(now=0.1)
    assert h.fake.writes == list(zip((0x26, 0x27), dsp.kt_encode_band(LESS_BASS)))
    assert h.fake.commits == 0


def test_live_edit_rejects_values_the_dsp_cannot_store():
    h = Harness()
    for index, band in ((5, BASS), (0, eq.FilterBand("lowpass", 100.0, 0.0, 0.7)),
                        (0, eq.FilterBand("peaking", 100.0, 12.5, 1.0))):
        try:
            h.svc.set_band_live(index, band)
        except ValueError:
            continue
        raise AssertionError(f"accepted band {index}: {band}")


def test_live_edits_made_while_unplugged_are_dropped():
    h = Harness()
    h.present = False
    h.svc.set_band_live(0, BASS)
    h.svc.run_once(now=0)
    h.present = True
    h.svc.run_once(now=1.0)
    assert "connected" in h.names() and h.fake.writes == []


def test_save_writes_commits_waits_for_restart_and_checks():
    h = Harness()
    h.svc.run_once(now=0)
    h.svc.save([BASS])
    h.svc.run_once(now=0.1)
    steps = [d["step"] for n, d in h.events if n == "save_progress"]
    assert steps == ["writing", "committing", "restarting", "verifying"]
    assert h.names()[-1] == "saved" and h.fake.commits == 1
    assert h.events[-1][1]["slot"] == dsp.KT_SLOT_ON
    assert h.fake.saved[0x26] == dsp.kt_encode_band(BASS)[0]


def test_save_with_read_back_mismatch_is_not_committed():
    h = Harness()
    h.svc.run_once(now=0)
    h.fake.ignore_writes_to = {0x26}
    h.svc.save([BASS])
    h.svc.run_once(now=0.1)
    assert h.events[-1] == ("save_failed", {"reason": "write_mismatch", "after_commit": False,
                                             "mismatched": [0]})
    assert h.fake.commits == 0 and h.svc.connected


def test_save_times_out_when_the_device_never_returns():
    h = Harness()
    h.svc.run_once(now=0)
    h.fake.on_commit = lambda: setattr(h, "present", False)
    h.svc.save([BASS])
    h.svc.run_once(now=0.1)
    assert h.events[-1] == ("save_failed", {"reason": "restart_timeout", "after_commit": True})
    assert not h.svc.connected


def test_save_queued_while_unplugged_runs_after_connect():
    h = Harness()
    h.present = False
    h.svc.save([BASS])
    h.svc.run_once(now=0)
    assert h.fake.commits == 0
    h.present = True
    h.svc.run_once(now=1.0)
    assert h.names()[-1] == "saved"


def test_eq_off_writes_slot_without_commit():
    h = Harness()
    h.svc.run_once(now=0)
    h.svc.set_eq_enabled(False)
    h.svc.run_once(now=0.1)
    assert h.fake.live[0x24][0] == dsp.KT_SLOT_OFF and h.fake.commits == 0
    assert h.events[-1] == ("eq_enabled", {"on": False})


def test_unplug_then_replug():
    h = Harness()
    h.svc.run_once(now=0)
    h.present = False
    h.svc.run_once(now=1.0)
    assert h.events[-1] == ("disconnected", {"reason": "unplugged"})
    assert not h.svc.connected
    h.present = True
    h.svc.run_once(now=2.0)
    assert h.names().count("connected") == 2


def test_worker_thread_connects_and_stops():
    h = Harness(sleep=time.sleep)
    h.svc.start()
    deadline = time.monotonic() + 2
    while "connected" not in h.names() and time.monotonic() < deadline:
        time.sleep(0.01)
    h.svc.stop()
    assert "connected" in h.names() and not h.svc.connected


def test_stop_lets_the_worker_thread_close_the_device():
    h = Harness(sleep=time.sleep)
    close_threads = []
    original_close = h.fake.close

    def record_close():
        close_threads.append(threading.current_thread().name)
        return original_close()

    h.fake.close = record_close
    h.svc.start()
    deadline = time.monotonic() + 2
    while "connected" not in h.names() and time.monotonic() < deadline:
        time.sleep(0.01)
    h.svc.stop()
    assert close_threads == ["chu2-device"]
    assert not h.svc.connected


# ---- Important 1: the worker thread must never die ---------------------- #
def test_worker_thread_survives_a_transport_exception_and_reconnects():
    h = Harness(sleep=time.sleep, poll_s=0.05)
    real_write = h.fake.write
    should_raise = {"armed": False}

    def flaky_write(report):
        if should_raise["armed"]:
            should_raise["armed"] = False
            raise RuntimeError("boom: unplugged mid-write")
        return real_write(report)

    h.fake.write = flaky_write
    h.svc.start()
    try:
        deadline = time.monotonic() + 2
        while "connected" not in h.names() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert "connected" in h.names()

        should_raise["armed"] = True
        h.svc.set_band_live(0, BASS)  # the next flush hits the flaky write

        deadline = time.monotonic() + 2
        while "disconnected" not in h.names() and time.monotonic() < deadline:
            time.sleep(0.01)

        assert _live_worker_threads(), "the worker thread died on a plain RuntimeError"
        assert "error" in h.names() and "disconnected" in h.names()

        # still present -> the worker should reconnect on its own
        deadline = time.monotonic() + 2
        while h.names().count("connected") < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert h.names().count("connected") == 2
    finally:
        h.svc.stop()


def test_failing_on_event_callback_does_not_kill_the_worker():
    fake = FakeChu2()
    present = {"value": True}
    events = []
    calls = {"n": 0}

    def open_():
        if not present["value"]:
            raise device_mod.UsbError("not plugged in")
        return fake

    def is_present():
        return present["value"]

    def flaky_on_event(name, data):
        events.append((name, data))
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("ui callback exploded")

    svc = DeviceService(open_, is_present, flaky_on_event, sleep=lambda s: None)
    svc.run_once(now=0)  # connect -> on_event raises; must not propagate
    assert [n for n, _ in events] == ["connected"]

    svc.set_eq_enabled(False)
    svc.run_once(now=0.1)  # the worker must still process the next job
    assert [n for n, _ in events][-1] == "eq_enabled"


# ---- deferred minor: start() guard --------------------------------------- #
def test_start_twice_is_a_no_op():
    h = Harness(sleep=time.sleep)
    h.svc.start()
    h.svc.start()
    deadline = time.monotonic() + 2
    while "connected" not in h.names() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(_live_worker_threads()) == 1
    h.svc.stop()
    assert not _live_worker_threads()


# ---- Minor 5: set_band_live stores a copy -------------------------------- #
def test_set_band_live_stores_a_copy():
    h = Harness()
    h.svc.run_once(now=0)
    band = eq.FilterBand("low_shelf", 100.0, 6.0, 0.7)
    h.svc.set_band_live(0, band)
    band.gain = 11.9  # mutate after validation; must not reach the device
    h.svc.run_once(now=0.1)
    assert h.fake.writes == list(
        zip((0x26, 0x27), dsp.kt_encode_band(eq.FilterBand("low_shelf", 100.0, 6.0, 0.7)))
    )


# ---- Important 3: save must not claim success without a restart --------- #
def test_save_without_a_restart_reports_no_restart():
    h = Harness()
    h.svc.run_once(now=0)
    h.fake.restarts_on_commit = False
    h.svc.save([BASS])
    h.svc.run_once(now=0.1)
    assert h.events[-1] == ("save_failed", {"reason": "no_restart", "after_commit": True})
    assert not h.svc.connected


# ---- Plan 2: save outcomes, still waiting, reopen retry, unknown types --- #
class FakeClock:
    """time.monotonic and time.sleep for tests: sleeping moves the clock."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _clocked(restart_polls):
    clock = FakeClock()
    plug = FakePlug(restart_polls=restart_polls)
    events = []
    svc = DeviceService(plug.open, plug.is_present, lambda n, d: events.append((n, d)),
                        sleep=clock.sleep, clock=clock)
    svc.run_once(now=0)
    return plug, svc, events


def test_still_waiting_after_8_s_then_saved():
    plug, svc, events = _clocked(restart_polls=60)  # away for 60 x 0.2 s = 12 s
    svc.save([BASS])
    svc.run_once(now=0.1)
    steps = [d["step"] for n, d in events if n == "save_progress"]
    assert steps == ["writing", "committing", "restarting", "still_waiting", "verifying"]
    assert events[-1][0] == "saved"


def test_save_gives_up_after_60_s():
    plug, svc, events = _clocked(restart_polls=10_000)
    svc.save([BASS])
    svc.run_once(now=0.1)
    assert [d["step"] for n, d in events if n == "save_progress"].count("still_waiting") == 1
    assert events[-1] == ("save_failed", {"reason": "restart_timeout", "after_commit": True})


def test_verify_retries_the_reopen():
    plug, svc, events = _clocked(restart_polls=1)
    real_open, calls = plug.open, {"n": 0}

    def flaky_open():
        calls["n"] += 1
        if plug.device.commits and calls["n"] == 2:  # first reopen after the restart
            raise device_mod.UsbError("not ready yet")
        return real_open()

    svc._open = flaky_open
    svc.save([BASS])
    svc.run_once(now=0.1)
    assert events[-1][0] == "saved"


def test_verify_mismatch_reports_what_was_stored():
    h = Harness()
    h.svc.run_once(now=0)
    h.fake.on_commit = lambda: h.fake.saved.update({0x26: bytes.fromhex("0a002800")})
    h.svc.save([BASS])
    h.svc.run_once(now=0.1)
    name, data = h.events[-1]
    assert name == "save_failed" and data["reason"] == "verify_mismatch" and data["after_commit"]
    assert data["bands"][0] == eq.FilterBand("low_shelf", 40.0, 1.0, 0.7)


def test_write_failure_is_reported_before_any_commit():
    h = Harness()
    h.svc.run_once(now=0)
    h.fake.silent = True
    h.svc.save([BASS])
    h.svc.run_once(now=0.1)
    failed = [d for n, d in h.events if n == "save_failed"][0]
    assert failed["reason"] == "write_failed" and not failed["after_commit"]
    assert h.names()[-1] == "disconnected" and h.fake.commits == 0


def test_invalid_bands_fail_before_writing():
    h = Harness()
    h.svc.run_once(now=0)
    h.svc.save([eq.FilterBand("lowpass", 100.0, 0.0, 0.7)])
    h.svc.run_once(now=0.1)
    assert h.events[-1][1]["reason"] == "invalid_bands" and h.fake.writes == []


def test_save_turns_the_eq_back_on_and_says_so():
    h = Harness()
    h.svc.run_once(now=0)
    h.svc.set_eq_enabled(False)
    h.svc.run_once(now=0.1)
    h.svc.save([BASS])
    h.svc.run_once(now=0.2)
    assert h.events[-1] == ("saved", {"bands": h.events[-1][1]["bands"], "slot": dsp.KT_SLOT_ON})


def test_unknown_filter_type_is_reported_once_until_a_replug():
    h = Harness()
    h.fake.live[0x27] = bytes.fromhex("f4010900")  # band 1 type code 9
    h.svc.run_once(now=0)
    h.svc.run_once(now=1.0)
    h.svc.run_once(now=2.0)
    assert h.events == [("error", {"code": "unknown_filter_type",
                                   "message": "unknown DSP filter type code 9"})]
    h.present = False
    h.svc.run_once(now=3.0)
    h.fake.live[0x27] = bytes.fromhex("f4010000")
    h.present = True
    h.svc.run_once(now=4.0)
    assert h.names()[-1] == "connected"


def test_stop_sends_pending_live_edits_and_eq_switch():
    h = Harness(sleep=time.sleep)
    h.svc.start()
    deadline = time.monotonic() + 2
    while "connected" not in h.names() and time.monotonic() < deadline:
        time.sleep(0.01)
    h.svc.set_band_live(0, BASS)
    h.svc.set_eq_enabled(True)
    h.svc.stop()
    assert (0x26, dsp.kt_encode_band(BASS)[0]) in h.fake.writes
    assert (0x24, bytes([dsp.KT_SLOT_ON, 0, 0, 0])) in h.fake.writes
    assert h.fake.closed
