"""The measured AutoEq tunings (brief S6, chu2.measured).

    python -m pytest -q tests/test_measured.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chu2 import dsp, eq, measured, transfer  # noqa: E402

# The shortfall each tuning has after 10 filters become 5. Asserted so a change to the
# picker in chu2.transfer shows up here as a number, not as a silent difference in sound.
GAP_DB = {
    "crinacle-711": 1.5,
    "crinacle-bk4620": 1.2,
    "hypethesonics": 1.4,
    "kazi": 1.4,
    "super-review": 2.4,
    "tonedeafmonk": 1.3,
}


def test_all_six_tunings_are_playable_on_the_chu2():
    items = measured.catalog()
    assert len(items) == 6
    for item in items:
        bands = [eq.FilterBand(b["type"], b["frequency"], b["gain"], b["q"]) for b in item["bands"]]
        assert len(bands) == dsp.KT_BANDS
        dsp.kt_fit_bands(bands)                      # raises if the CHU 2 cannot play it
        assert all(abs(b.gain) <= dsp.KT_GAIN_LIMIT_DB for b in bands)
        assert all(b.type in ("peaking", "low_shelf", "high_shelf") for b in bands)


def test_each_tuning_keeps_its_measured_shortfall():
    for tuning in measured.TUNINGS:
        assert transfer.read_text(tuning["text"])["gap_db"] == GAP_DB[tuning["id"]], tuning["id"]


def test_the_cards_name_the_measurer_and_the_shortfall():
    about = {item["id"]: item["about"] for item in measured.catalog()}
    assert "crinacle" in about["measured:crinacle-711"]
    assert "711" in about["measured:crinacle-711"]
    assert "1.5 dB" in about["measured:crinacle-711"]
    for item in measured.catalog():
        assert item["group"] == "measured" and "Measured" in item["tags"]


def test_the_six_tunings_differ_from_each_other():
    """Six measurements of the same earphone, so six different corrections."""
    shapes = {tuple((b["type"], b["frequency"], b["gain"], b["q"]) for b in item["bands"])
              for item in measured.catalog()}
    assert len(shapes) == 6


def test_reading_the_tunings_happens_once_and_is_never_shared():
    """Reducing ten filters to five costs ~90 ms, and the library asks often."""
    measured.catalog()
    before = measured._computed.cache_info()
    measured.catalog()
    after = measured._computed.cache_info()
    assert after.misses == before.misses, "the tunings were read again"

    first, second = measured.catalog(), measured.catalog()
    first[0]["favourite"] = True
    first[0]["bands"][0]["gain"] = 99.0
    first[0]["tags"].append("scribbled on")
    assert "favourite" not in second[0]
    assert second[0]["bands"][0]["gain"] != 99.0
    assert "scribbled on" not in second[0]["tags"]
