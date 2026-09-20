"""Hold an audio stream open so the CHU 2 stops clicking (test #36).

The CHU 2 mutes its own amplifier whenever nothing is playing, and clicks when it
switches back on, so a video, a track or even a notification starts with a pop.
Looping one second of silence keeps the stream open and the amplifier engaged.

``winsound`` is part of the standard library on Windows and absent everywhere
else, so :func:`available` is False off Windows and the tests replace the module.

ponytail: silence through winsound, no audio library and no service. It plays to
whatever Windows has as the default output, so switching headphones stops it
working until it is turned off and on again.
"""

from __future__ import annotations

import logging
import os
import struct
import tempfile
import wave
from typing import Any, Optional

logger = logging.getLogger(__name__)

RATE = 48_000  # what Windows already runs the CHU 2 at
SECONDS = 1
FILENAME = "chu2_silence.wav"

try:  # pragma: no cover - the import itself is the platform check
    import winsound as _player  # type: ignore
except ImportError:  # pragma: no cover
    _player = None  # type: ignore

player: Optional[Any] = _player
_running = False


def available() -> bool:
    """True where silence can be played at all (Windows)."""
    return player is not None


def running() -> bool:
    return _running


def silence_path() -> str:
    """Write the silent clip if it isn't there, and return its path."""
    path = os.path.join(tempfile.gettempdir(), FILENAME)
    if not os.path.exists(path):
        with wave.open(path, "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(RATE)
            handle.writeframes(struct.pack("<h", 0) * 2 * RATE * SECONDS)
    return path


# What gets written into the Startup folder. A .pyw runs through pythonw, so there is no
# console window and no shortcut, no COM and no .vbs to go wrong. Deleting the file is how
# the switch turns off. Kept as one string so the silence has a single source in the repo.
STARTUP_NAME = "CHU 2 - stop the clicking.pyw"
STARTUP_SOURCE = f"""# Written by CHU 2 Studio: Settings -> Clicking -> start with Windows.
# Delete this file, or turn the switch off in the app, to stop it.
import struct, os, tempfile, time, wave, winsound

path = os.path.join(tempfile.gettempdir(), {FILENAME!r})
with wave.open(path, "wb") as handle:
    handle.setnchannels(2)
    handle.setsampwidth(2)
    handle.setframerate({RATE})
    handle.writeframes(struct.pack("<h", 0) * 2 * {RATE} * {SECONDS})
winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
while True:
    time.sleep(3600)
"""


def startup_dir() -> str:
    """Where Windows looks for things to run at login."""
    return os.path.join(os.environ.get("APPDATA", tempfile.gettempdir()),
                        "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def startup_path() -> str:
    return os.path.join(startup_dir(), STARTUP_NAME)


def startup_enabled() -> bool:
    return os.path.exists(startup_path())


def enable_startup() -> bool:
    """Write the login file. True if it is there afterwards."""
    try:
        os.makedirs(startup_dir(), exist_ok=True)
        with open(startup_path(), "w", encoding="utf-8") as handle:
            handle.write(STARTUP_SOURCE)
    except OSError as exc:
        logger.warning("could not write the startup file: %s", exc)
        return False
    return True


def disable_startup() -> None:
    try:
        os.remove(startup_path())
    except FileNotFoundError:
        pass
    except OSError as exc:  # pragma: no cover
        logger.warning("could not remove the startup file: %s", exc)


def start() -> bool:
    """Loop silence. True if it is now playing."""
    global _running
    if player is None:
        return False
    if _running:
        return True
    try:
        player.PlaySound(silence_path(),
                         player.SND_FILENAME | player.SND_ASYNC | player.SND_LOOP)
    except (OSError, RuntimeError) as exc:
        logger.warning("could not start the silence: %s", exc)
        return False
    _running = True
    return True


def stop() -> None:
    global _running
    if player is not None and _running:
        try:
            player.PlaySound(None, player.SND_PURGE)
        except (OSError, RuntimeError) as exc:  # pragma: no cover
            logger.warning("could not stop the silence: %s", exc)
    _running = False
