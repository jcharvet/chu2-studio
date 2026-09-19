"""Offline checks for the KTMicro DSP protocol (no device needed).

    python tests/test_ktmicro.py        (or: pytest tests)
"""

import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chu2 import dsp, eq, preset  # noqa: E402

CAP = bytes.fromhex


def test_packets_match_real_chu2_capture():
    # Bytes from a real CHU 2 (devicePEQ tests/captures/ktmicro_chu2_dsp.json).
    gain_freq, q_type = dsp.kt_encode_band(eq.FilterBand("low_shelf", 200, -3.0, 2.0))
    assert dsp.kt_packet(0x28, dsp.KT_WRITE, gain_freq) == CAP("28 00 00 00 57 00 e2 ff c8 00")
    assert dsp.kt_packet(0x29, dsp.KT_WRITE, q_type) == CAP("29 00 00 00 57 00 d0 07 03 00")
    assert dsp.kt_packet(0x26, dsp.KT_READ) == CAP("26 00 00 00 52 00 00 00 00 00")
    assert dsp.kt_packet(0x00, dsp.KT_COMMIT) == CAP("00 00 00 00 53 00 00 00 00 00")
    # Band 1 as read from our unit on 2026-09-18.
    band = dsp.kt_decode_band(CAP("f1 ff 28 00"), CAP("f4 01 00 00"))
    assert (band.type, band.frequency, band.gain, band.q) == ("peaking", 40, -1.5, 0.5)


def test_fit_bands():
    fitted = dsp.kt_fit_bands([eq.FilterBand("high_shelf", 8000, 2.0, 0.7)])
    assert len(fitted) == 5 and all(b.gain == 0 for b in fitted[1:])
    too_many = [eq.FilterBand()] * 6
    bad_cases = (
        too_many,
        [eq.FilterBand("lowpass", 100, 0, 1)],
        [eq.FilterBand(gain=12.5)],
        [eq.FilterBand(frequency=19.9)],            # below 20 Hz
        [eq.FilterBand(frequency=20_000.1)],         # above 20000 Hz
        [eq.FilterBand(q=0.0004)],                   # below 0.1 (the Q=0-to-the-chip bug)
        [eq.FilterBand(q=10.5)],                     # above 10 (UI range, not the chip's 65)
        [eq.FilterBand(frequency=float("nan"))],
        [eq.FilterBand(frequency=float("inf"))],
        [eq.FilterBand(gain=float("nan"))],
        [eq.FilterBand(gain=float("inf"))],
        [eq.FilterBand(q=float("nan"))],
        [eq.FilterBand(q=float("inf"))],
    )
    for bad in bad_cases:
        try:
            dsp.kt_fit_bands(bad)
        except ValueError:
            continue
        raise AssertionError(f"kt_fit_bands accepted {bad}")


def test_fit_bands_accepts_every_shipped_preset():
    """Every JSON preset under presets/ must still pass the DSP's range checks.

    Presets with more than 5 bands (e.g. chu_2_crinacle.json) already fail the
    pre-existing band-count limit, unrelated to the range validation this test
    is guarding, so only the first 5 bands of each preset are fitted here.
    """
    preset_dir = os.path.join(os.path.dirname(__file__), "..", "presets")
    paths = sorted(glob.glob(os.path.join(preset_dir, "*.json")) +
                   glob.glob(os.path.join(preset_dir, "user_presets", "*.json")))
    assert paths, "no preset JSON files found"
    for path in paths:
        loaded = preset.load(path)
        dsp.kt_fit_bands(loaded.bands[:dsp.KT_BANDS])


if __name__ == "__main__":
    test_packets_match_real_chu2_capture()
    test_fit_bands()
    test_fit_bands_accepts_every_shipped_preset()
    print("OK")
