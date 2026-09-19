"""A fake CHU 2 DSP that behaves like our unit, for tests and ``--fake-device``.

``FakeChu2`` implements the transport contract of ``chu2.dsp.kt_command``:
``write(report)`` and ``read(length, timeout_ms)`` (``b""`` on timeout).
Registers start with the EQ read from our unit on 2026-09-18.

``FakePlug`` is the USB plug around it: ``open()`` / ``is_present()`` have the
shape ``DeviceService`` expects, the plug can be pulled (``present = False``),
and after a commit the CHU 2 drops off USB for ``restart_polls`` presence
checks and comes back playing its saved EQ, like the real one (tests #15, #16).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Set, Tuple

from . import device as device_mod, dsp

_START: Dict[int, bytes] = {
    0x24: bytes([0x03, 0, 0, 0]),  # EQ slot: on
    0x26: bytes.fromhex("f1ff2800"), 0x27: bytes.fromhex("f4010000"),  # 40 Hz -1.5 dB Q0.5
    0x28: bytes.fromhex("c4ffc800"), 0x29: bytes.fromhex("58020000"),  # 200 Hz -6.0 dB Q0.6
    0x2A: bytes.fromhex("e7ff7805"), 0x2B: bytes.fromhex("40060000"),  # 1400 Hz -2.5 dB Q1.6
    0x2C: bytes.fromhex("d0ffac0d"), 0x2D: bytes.fromhex("e8030000"),  # 3500 Hz -4.8 dB Q1.0
    0x2E: bytes.fromhex("ecff2823"), 0x2F: bytes.fromhex("dc050000"),  # 9000 Hz -2.0 dB Q1.5
    0x66: bytes([0x00, 0x02, 0, 0]),  # pregain as read
}
_ACK = bytes([0x03, 0, 0, 0])  # our unit answers every write and commit with 03


class FakeChu2:
    def __init__(self) -> None:
        self.live: Dict[int, bytes] = dict(_START)   # what the DSP plays now
        self.saved: Dict[int, bytes] = dict(_START)  # what survives a restart
        self.writes: List[Tuple[int, bytes]] = []    # every write command, in order
        self.commits = 0
        self.ignore_writes_to: Set[int] = set()      # writes acked but dropped
        self.silent = False                          # never answers
        self.restarts_on_commit = True               # False: ack a commit but never drop off USB
        self.pending_restart = False                 # set by a commit
        self.on_commit: Optional[Callable[[], None]] = None
        self.closed = False
        self._replies: List[bytes] = []

    # -- transport contract ------------------------------------------------- #
    def write(self, report: bytes) -> int:
        if self.closed:
            raise device_mod.UsbError("fake CHU 2: write after close")
        report = bytes(report)
        assert report[0] == dsp.KT_REPORT_ID and len(report) == 11, report.hex(" ")
        reg, cmd, value = report[1], report[5], report[7:11]
        if self.silent:
            return len(report)
        if cmd == dsp.KT_READ:
            answer = self.live.get(reg, bytes(4))
        elif cmd == dsp.KT_WRITE:
            self.writes.append((reg, value))
            if reg not in self.ignore_writes_to:
                self.live[reg] = value
            answer = _ACK
        elif cmd == dsp.KT_COMMIT:
            self.commits += 1
            self.saved = dict(self.live)
            if self.restarts_on_commit:
                self.pending_restart = True
            if self.on_commit is not None:
                self.on_commit()
            answer = _ACK
        else:
            return len(report)  # unknown command: the real chip stays silent
        self._replies.append(bytes([dsp.KT_REPORT_ID, reg, 0, 0, 0, cmd, 0]) + answer)
        return len(report)

    def read(self, length: int = 64, timeout: int = 1000) -> bytes:
        if self.closed:
            raise device_mod.UsbError("fake CHU 2: read after close")
        return self._replies.pop(0) if self._replies else b""

    # -- helpers ------------------------------------------------------------- #
    def restart(self) -> None:
        """What happens after a commit on hardware: play the saved EQ."""
        self.live = dict(self.saved)
        self._replies.clear()

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "FakeChu2":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


class FakePlug:
    """The USB plug around a :class:`FakeChu2`; pass ``open`` and
    ``is_present`` to ``DeviceService``."""

    def __init__(self, device: Optional[FakeChu2] = None, present: bool = True,
                 restart_polls: int = 1) -> None:
        self.device = device if device is not None else FakeChu2()
        self.present = present
        self.restart_polls = restart_polls  # presence checks that miss the CHU 2 after a commit
        self._gone_polls = 0

    def open(self) -> FakeChu2:
        if not self.present or self._gone_polls:
            raise device_mod.UsbError("fake CHU 2 is not plugged in")
        self.device.closed = False
        return self.device

    def is_present(self) -> bool:
        if self.device.pending_restart:  # the real CHU 2 drops off USB once per commit
            self.device.pending_restart = False
            self.device.restart()
            self._gone_polls = self.restart_polls
        if self._gone_polls:
            self._gone_polls -= 1
            return False
        return self.present
