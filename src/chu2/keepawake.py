"""Keep the CHU 2's amplifier awake, so it stops clicking (test #36, #37).

The CHU 2 mutes its own amplifier when it sees no audio for about half a minute,
and clicks when it switches back on, so a video, a track or even a notification
starts with a pop.

What does *not* work, all tried on the hardware: a looping silent clip through
``winsound``, the same clip carrying a one-bit dither, and a continuous stream of
that dither. The chip is not watching for an open stream, it is watching the
signal level, and -90 dBFS does not count.

What works is a 5 Hz tone at -70 dBFS. Five hertz is well below hearing, and quiet
enough that a sealed earphone does not turn it into anything you notice.

The level matters more than it looks. Sealed in an ear canal the driver acts as a
pressure source, not as a speaker in a room, so infrasound *does* reach you: at
-45 dBFS the owner heard it as wings flapping, five times a second. -70 dBFS is
inaudible and the chip still counts it.

``sounddevice`` is imported when the tone starts, not when this module is, so the
tests and the CLI never need it. The stream is opened on the CHU 2 by name rather
than on whatever Windows calls the default output, so switching headphones does
not quietly stop it working.

ponytail: array and math build one cycle, no numpy, which would have cost about
15 MB in the .exe for one sine wave.
"""

from __future__ import annotations

import array
import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)

RATE = 48_000       # what Windows already runs the CHU 2 at
TONE_HZ = 5.0       # below hearing, and below what the driver can reproduce
# Found by bracketing on the hardware: -90 dBFS is too quiet for the chip to notice,
# -45 dBFS is loud enough for the owner to hear as a flutter, -70 dBFS is neither.
# ponytail: one constant, no setting. If another CHU 2 ignores -70, raise it - but not
# past about -60, which is where five flaps a second start to be audible again.
TONE_DBFS = -70.0
DEVICE_HINT = "Chu2"
BLOCKSIZE = 1024

backend: Optional[Any] = None   # the tests put a stand-in here
_stream: Any = None


def _sounddevice() -> Any:
    global backend
    if backend is None:
        import sounddevice  # noqa: PLC0415 - only when the tone is actually wanted

        backend = sounddevice
    return backend


def available() -> bool:
    """True where the tone can be played at all."""
    try:
        _sounddevice()
    except Exception as exc:  # pragma: no cover - depends on the machine
        logger.debug("no audio output: %s", exc)
        return False
    return True


def running() -> bool:
    return _stream is not None


def one_cycle() -> bytes:
    """One whole cycle of the tone, stereo 16-bit. 5 Hz at 48 kHz is 9600 samples."""
    peak = int(32767 * 10 ** (TONE_DBFS / 20))
    frames = int(RATE / TONE_HZ)
    samples = array.array("h")
    for n in range(frames):
        value = int(peak * math.sin(2 * math.pi * n / frames))
        samples.append(value)
        samples.append(value)
    return samples.tobytes()


def _find_device(sd: Any) -> Optional[int]:
    """The CHU 2 itself, not whatever Windows calls the default output."""
    try:
        for index, device in enumerate(sd.query_devices()):
            if DEVICE_HINT in device["name"] and device["max_output_channels"] > 0:
                return index
    except Exception as exc:  # pragma: no cover
        logger.debug("could not list the sound devices: %s", exc)
    return None


def start() -> bool:
    """Play the tone. True if it is now playing."""
    global _stream
    if _stream is not None:
        return True
    try:
        sd = _sounddevice()
    except Exception as exc:
        # No sound card at all is a fact about the machine, not a fault to warn about.
        logger.debug("no audio output: %s", exc)
        return False
    try:
        cycle = one_cycle()
        span = len(cycle)
        position = 0

        def callback(out: Any, frames: int, _time: Any, _status: Any) -> None:
            nonlocal position
            need = frames * 4  # two channels of 16-bit
            chunk = bytearray()
            while len(chunk) < need:
                take = min(need - len(chunk), span - position)
                chunk += cycle[position:position + take]
                position = (position + take) % span
            out[:] = bytes(chunk)

        stream = sd.RawOutputStream(device=_find_device(sd), samplerate=RATE, channels=2,
                                    dtype="int16", callback=callback, blocksize=BLOCKSIZE)
        stream.start()
    except Exception as exc:
        logger.warning("the CHU 2 will click before every sound: %s", exc)
        return False
    _stream = stream
    logger.info("playing a %.0f Hz tone at %.0f dBFS, so the CHU 2 will not click",
                TONE_HZ, TONE_DBFS)
    return True


def stop() -> None:
    global _stream
    if _stream is None:
        return
    logger.info("stopped the tone, so the CHU 2 will click again")
    try:
        _stream.stop()
        _stream.close()
    except Exception as exc:  # pragma: no cover
        logger.warning("could not stop the tone: %s", exc)
    _stream = None
