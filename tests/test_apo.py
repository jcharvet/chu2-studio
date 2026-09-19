"""Offline checks for `chu2 apo apply/restore` on a fake Equalizer APO folder.

    python tests/test_apo.py        (or: pytest tests)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chu2 import cli  # noqa: E402

PRESETS = os.path.join(os.path.dirname(__file__), "..", "presets")


def _write(folder, name, text):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
        handle.write(text)


def _read(folder, name):
    with open(os.path.join(folder, name), "r", encoding="utf-8") as handle:
        return handle.read()


def _apo(folder, *argv):
    config = os.path.join(folder, "config.txt")
    assert cli.main(["--presets-dir", PRESETS, "apo", *argv, "--config-path", config]) == 0


def test_second_apply_keeps_the_peace_backup():
    with tempfile.TemporaryDirectory() as folder:
        _write(folder, "config.txt", "Include: peace.txt\n")
        _write(folder, "peace.txt", "Device: Chu2 DSP Headphones {x}\nChannel: all\nPreamp: -4 dB\n")
        _apo(folder, "apply", "chu_2_custom")
        _apo(folder, "apply", "custom_warm")
        assert _read(folder, "config.txt.bak") == "Include: peace.txt\n"
        assert _read(folder, "chu2studio.txt").startswith(
            "Device: Chu2 DSP Headphones {x}\nChannel: all\n# Custom Warm")
        _apo(folder, "restore")
        assert _read(folder, "config.txt") == "Include: peace.txt\n"


def test_device_line_in_config_txt_itself_is_kept():
    with tempfile.TemporaryDirectory() as folder:
        _write(folder, "config.txt", "# only the CHU 2\nDevice: Chu2 DSP\n"
                                     "Include: chu2-custom.txt\n# Include: chu2-crinacle.txt\n")
        _write(folder, "chu2-custom.txt", "Preamp: -4 dB\n")
        _apo(folder, "apply", "chu_2_custom")
        assert _read(folder, "chu2studio.txt").startswith("Device: Chu2 DSP\n# CHU 2 Custom")


if __name__ == "__main__":
    test_second_apply_keeps_the_peace_backup()
    test_device_line_in_config_txt_itself_is_kept()
    print("OK")
