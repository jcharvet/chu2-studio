"""Shared test fixtures (Minor 9): keep every test off the real CHU 2.

A real CHU 2 may be plugged in while tests run. Even a test that forgets to
patch the transport must never open it, so this autouse fixture makes
``HidTransport.open`` and ``hid_present`` raise until a test patches them
itself (a test's own later ``monkeypatch.setattr`` overrides this, as
``tests/test_cli_dsp.py`` does).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

from chu2 import dsp  # noqa: E402


def _refuse(*_args, **_kwargs):
    raise RuntimeError("tests must not open the real CHU 2; patch HidTransport.open")


@pytest.fixture(autouse=True)
def _no_real_chu2(monkeypatch):
    monkeypatch.setattr(dsp.HidTransport, "open", classmethod(_refuse))
    monkeypatch.setattr(dsp, "hid_present", _refuse)
