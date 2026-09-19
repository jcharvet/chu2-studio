"""Owns the CHU 2 connection on one worker thread (spec §4.2).

The GUI never touches USB. It calls the public methods, which only queue work
and are safe from any thread, and it receives events through
``on_event(name, data)``:

    connected       {"slot": int, "bands": [FilterBand x 5]}
    disconnected    {"reason": str}
    error           {"code": "open_failed" | "unknown_filter_type" | "internal",
                     "message": str}
    eq_enabled      {"on": bool}
    save_progress   {"step": "writing" | "committing" | "restarting"
                             | "still_waiting" | "verifying"}
    saved           {"bands": [FilterBand x 5], "slot": int}
    save_failed     {"reason": str, "after_commit": bool, ...}

``save_failed`` reasons. Before the commit nothing was saved:
``invalid_bands`` (+ "message"), ``write_failed`` (+ "message"; the
connection is dropped), ``write_mismatch`` (+ "mismatched": [band indexes]).
After the commit the outcome is unknown until the CHU 2 is read again:
``commit_unknown`` (+ "message"; dropped), ``no_restart`` (it never dropped off
USB), ``restart_timeout`` (it did not come back within ``restart_timeout_s``),
``verify_unavailable`` (+ "message"; it came back but could not be read),
``verify_mismatch`` (+ "bands": what it stored).

A save emits ``save_progress {"step": "still_waiting"}`` once when the CHU 2 has
been away for ``still_waiting_s`` (brief S8 C) and keeps waiting up to
``restart_timeout_s``, so the user can unplug and replug it.

``on_event`` runs on the worker thread. It must return quickly and never
block: a slow or blocking callback stalls live edits and polling. A callback
that raises is caught and logged; it never kills the worker (see :meth:`_emit`).

Tests drive :meth:`run_once` directly instead of starting the thread.
"""

from __future__ import annotations

import dataclasses
import logging
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import device as device_mod, dsp, eq

EventSink = Callable[[str, Dict[str, Any]], None]

logger = logging.getLogger(__name__)


class DeviceService:
    def __init__(
        self,
        open_transport: Callable[[], Any],
        is_present: Callable[[], bool],
        on_event: EventSink,
        poll_s: float = 1.0,
        restart_timeout_s: float = 60.0,
        still_waiting_s: float = 8.0,
        reopen_tries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._open = open_transport
        self._is_present = is_present
        self._on_event = on_event
        self._poll_s = poll_s
        self._restart_timeout_s = restart_timeout_s
        self._still_waiting_s = still_waiting_s
        self._reopen_tries = reopen_tries
        self._sleep = sleep
        self._clock = clock
        self._transport: Any = None
        self._blocked = False  # an unknown filter type: wait for a replug
        self._jobs: "queue.Queue[tuple]" = queue.Queue()
        self._live: Dict[int, eq.FilterBand] = {}
        self._lock = threading.Lock()
        self._next_poll = 0.0
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- public: safe from any thread ------------------------------------- #
    @property
    def connected(self) -> bool:
        return self._transport is not None

    def start(self) -> None:
        """Start the worker thread. A no-op if one is already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._loop, name="chu2-device", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the worker. It first sends pending live edits and EQ on/off
        switches (a queued save is dropped), then closes the transport itself.

        If no worker was started (single-threaded use via run_once), finish
        here since there's no worker thread to do it.
        """
        self._stop_flag.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        else:
            self._finish()

    def set_band_live(self, index: int, band: eq.FilterBand) -> None:
        """Play ``band`` on slot ``index`` (0-4) now, without saving it."""
        if not 0 <= index < dsp.KT_BANDS:
            raise ValueError(f"band index {index} is outside 0-{dsp.KT_BANDS - 1}")
        dsp.kt_fit_bands([band])  # ValueError for a type or gain the DSP can't store
        with self._lock:
            self._live[index] = dataclasses.replace(band)  # latest value wins; caller can't mutate it later

    def set_eq_enabled(self, on: bool) -> None:
        self._jobs.put(("eq_enabled", on))

    def save(self, bands: Sequence[eq.FilterBand]) -> None:
        """Write, verify, commit, wait for the restart, and check again."""
        self._jobs.put(("save", list(bands)))

    # ---- worker ------------------------------------------------------------ #
    def _loop(self) -> None:
        try:
            while not self._stop_flag.is_set():
                try:
                    self.run_once()
                except Exception as exc:  # last line of defence: never kill the worker
                    logger.exception("chu2 device worker: unhandled error in run_once")
                    self._emit("error", {"code": "internal", "message": str(exc)})
                    self._drop("internal error")
                self._stop_flag.wait(0.05)  # live edits reach the device within ~50 ms
        finally:
            self._finish()  # always on the worker thread, never from the caller

    def _finish(self) -> None:
        """Send pending live edits and EQ on/off switches, then close."""
        if self._transport is not None:
            try:
                self._flush_live()
                while True:
                    job = self._jobs.get_nowait()
                    if job[0] == "eq_enabled":
                        self._do_eq_enabled(*job[1:])
            except (queue.Empty, device_mod.UsbError):
                pass
        self._close()

    def _emit(self, name: str, data: Dict[str, Any]) -> None:
        """Call ``on_event``, guarding the worker from a callback that raises."""
        try:
            self._on_event(name, data)
        except Exception:
            logger.exception("chu2 device worker: on_event callback raised for %r", name)

    def run_once(self, now: Optional[float] = None) -> None:
        now = self._clock() if now is None else now
        if now >= self._next_poll:
            self._next_poll = now + self._poll_s
            self._check_connection()
        if self._transport is None:
            return  # queued jobs wait for the device
        try:
            self._flush_live()
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            getattr(self, "_do_" + job[0])(*job[1:])
        except device_mod.UsbError as exc:
            self._drop(str(exc))

    def _check_connection(self) -> None:
        present = self._is_present()
        if not present:
            self._blocked = False  # a replug may bring a CHU 2 we can read
        if self._transport is not None and not present:
            self._drop("unplugged")
        elif self._transport is None and present and not self._blocked:
            self._connect()

    def _connect(self) -> None:
        try:
            self._transport = self._open()
            slot, bands = dsp.kt_read_eq(self._transport)
        except dsp.UnknownFilterType as exc:
            self._close()
            self._blocked = True  # report once, not every second
            self._emit("error", {"code": "unknown_filter_type", "message": str(exc)})
            return
        except device_mod.UsbError as exc:
            self._close()
            self._emit("error", {"code": "open_failed", "message": str(exc)})
            return
        with self._lock:
            self._live.clear()  # edits made while unplugged never reach the device
        self._emit("connected", {"slot": slot, "bands": bands})

    def _flush_live(self) -> None:
        with self._lock:
            pending, self._live = self._live, {}
        for index, band in sorted(pending.items()):
            dsp.kt_write_band(self._transport, index, band)

    def _do_eq_enabled(self, on: bool) -> None:
        dsp.kt_set_slot(self._transport, dsp.KT_SLOT_ON if on else dsp.KT_SLOT_OFF)
        self._emit("eq_enabled", {"on": on})

    # ---- save ------------------------------------------------------------- #
    def _do_save(self, bands: List[eq.FilterBand]) -> None:
        def step(name: str) -> None:
            self._emit("save_progress", {"step": name})

        def fail(reason: str, after_commit: bool, **extra: Any) -> None:
            self._emit("save_failed", dict({"reason": reason, "after_commit": after_commit}, **extra))

        try:
            bands = dsp.kt_fit_bands(bands)
        except ValueError as exc:
            fail("invalid_bands", False, message=str(exc))
            return
        step("writing")
        try:
            mismatched = self._write_and_check(bands)
        except device_mod.UsbError as exc:
            fail("write_failed", False, message=str(exc))
            self._drop(str(exc))
            return
        if mismatched:
            fail("write_mismatch", False, mismatched=mismatched)  # never commit a mismatch
            return
        step("committing")
        try:
            dsp.kt_commit(self._transport)
        except device_mod.UsbError as exc:
            fail("commit_unknown", True, message=str(exc))
            self._drop(str(exc))
            return
        self._close()
        step("restarting")
        failure = self._wait_for_restart(step)
        if failure is not None:
            fail(failure, True)
            return
        step("verifying")
        try:
            slot, stored = self._reopen_and_read()
        except device_mod.UsbError as exc:
            fail("verify_unavailable", True, message=str(exc))
            return
        if [dsp.kt_encode_band(b) for b in stored] != [dsp.kt_encode_band(b) for b in bands]:
            fail("verify_mismatch", True, bands=stored)
            return
        self._emit("saved", {"bands": stored, "slot": slot})

    def _write_and_check(self, bands: List[eq.FilterBand]) -> List[int]:
        """Switch the EQ on if it is off, write every band live, read each back.
        Returns the indexes whose read-back differs (empty when all match)."""
        t = self._transport
        slot = dsp.kt_command(t, dsp.kt_packet(dsp.KT_REG_SLOT, dsp.KT_READ,
                                               bytes([dsp.KT_SLOT_ON, 0, 0, 0])))[0]
        if slot == dsp.KT_SLOT_OFF:
            dsp.kt_set_slot(t, dsp.KT_SLOT_ON)
        return [i for i, band in enumerate(bands)
                if not dsp.kt_verify_band(t, i, dsp.kt_write_band(t, i, band))]

    def _wait_for_restart(self, step: Callable[[str], None]) -> Optional[str]:
        """After a commit the CHU 2 drops off USB and returns (~1-1.5 s).

        Returns ``None`` on a successful restart, or a failure reason:
        ``"no_restart"`` if the device never vanished before the deadline (the
        commit was acked but nothing confirms it was saved), or
        ``"restart_timeout"`` if it vanished but did not come back in time.
        """
        start = self._clock()
        gone = False
        told = False
        while self._clock() - start < self._restart_timeout_s:
            if not self._is_present():
                gone = True
            elif gone:
                return None
            if not told and self._clock() - start >= self._still_waiting_s:
                step("still_waiting")
                told = True
            self._sleep(0.2)
        return "restart_timeout" if gone else "no_restart"

    def _reopen_and_read(self) -> Tuple[int, List[eq.FilterBand]]:
        """Open and read the CHU 2 after its restart; Windows may need a moment."""
        for attempt in range(self._reopen_tries):
            try:
                self._transport = self._open()
                return dsp.kt_read_eq(self._transport)
            except device_mod.UsbError:
                self._close()
                if attempt == self._reopen_tries - 1:
                    raise
                self._sleep(0.5)
        raise device_mod.UsbError("reopen_tries must be at least 1")

    def _drop(self, reason: str) -> None:
        self._close()
        self._emit("disconnected", {"reason": reason})

    def _close(self) -> None:
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
        self._transport = None
