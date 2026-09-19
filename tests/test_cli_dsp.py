"""`chu2 dsp` commands against a fake CHU 2 (no device needed).

    python -m pytest -q tests/test_cli_dsp.py
"""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chu2 import cli, dsp  # noqa: E402
from chu2.fake_device import FakeChu2  # noqa: E402

PRESETS = os.path.join(os.path.dirname(__file__), "..", "presets")


def _use_fake(monkeypatch):
    fake = FakeChu2()
    monkeypatch.setattr(dsp.HidTransport, "open", classmethod(lambda cls: fake))
    return fake


def test_dsp_read_goes_through_hid(monkeypatch, capsys):
    _use_fake(monkeypatch)
    assert cli.main(["dsp", "read"]) == 0
    out = capsys.readouterr().out
    assert "EQ slot: 0x03 (on)" in out and "3500.0" in out


def test_dsp_write_backs_up_then_saves(monkeypatch, tmp_path):
    fake = _use_fake(monkeypatch)
    shutil.copy(os.path.join(PRESETS, "custom_warm.json"), tmp_path)
    assert cli.main(["--presets-dir", str(tmp_path), "dsp", "write", "custom_warm"]) == 0
    assert fake.commits == 1
    backup = json.loads((tmp_path / "chu2_hardware_backup.json").read_text(encoding="utf-8"))
    assert backup["bands"][1]["gain"] == -6.0  # the EQ the fake had before
