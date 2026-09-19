"""The pyusb research tools live in chu2.research, apart from the app.

    python -m pytest -q tests/test_research.py
"""

import os
import subprocess
import sys

from chu2 import cli, device as device_mod, research

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")


def test_cli_probe_goes_through_the_research_module(monkeypatch, capsys):
    def no_driver(cls):
        raise device_mod.UsbError("no Zadig driver on interface 3")

    monkeypatch.setattr(research.DspTransport, "open", classmethod(no_driver))
    assert cli.main(["probe"]) != 0
    printed = capsys.readouterr()
    assert "no Zadig driver on interface 3" in printed.out + printed.err


def test_the_app_never_loads_the_research_code_or_pyusb():
    code = ("import sys, chu2.app.main, chu2.app.api; "
            "print('chu2.research' in sys.modules, 'usb' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         env=dict(os.environ, PYTHONPATH=SRC)).stdout.split()
    assert out == ["False", "False"]
