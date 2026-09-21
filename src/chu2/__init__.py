"""Moondrop CHU 2 DSP — open-source control tool.

This package provides:

* ``device``  — USB discovery and descriptor inspection (pyusb).
* ``dsp``     — DSP transport and probing on interface 3 (endpoints 0x03/0x83).
* ``eq``      — Parametric EQ model and RBJ biquad filter math.
* ``preset``  — Preset load/save/validate and export (EqualizerAPO, JSON).
* ``cli``     — Command-line interface.
* ``gui``     — Tkinter graphical interface.
"""

from __future__ import annotations

__version__ = "0.2.1"

__all__ = ["__version__"]
