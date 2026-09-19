"""Automatic preamp from the EQ bands (spec §4.4).

    python -m pytest -q tests/test_preamp.py
"""

import itertools

from chu2 import eq, preamp

FB = eq.FilterBand
# Brief §3.5 idle slots (0 dB): LS 105, PK 250, PK 1k, PK 4k, HS 10k
IDLE = [FB("low_shelf", 105.0, 0.0, 0.71), FB("peaking", 250.0, 0.0, 1.0),
        FB("peaking", 1000.0, 0.0, 1.0), FB("peaking", 4000.0, 0.0, 1.4),
        FB("high_shelf", 10000.0, 0.0, 0.71)]
# The owner's "Warm Bass" (presets/user_presets/warm_bass.json is git-ignored)
WARM_BASS = [FB("peaking", 40.0, -1.5, 0.5), FB("low_shelf", 100.0, 6.0, 0.7),
             FB("peaking", 1400.0, -2.5, 1.6), FB("peaking", 3500.0, -4.8, 1.0),
             FB("peaking", 9000.0, -2.0, 1.5)]
FREQS = eq.log_frequency_axis(20.0, 20000.0, 200)


def _with(**slots):
    bands = list(IDLE)
    for key, band in slots.items():
        bands[int(key[1:])] = band
    return bands


def test_shelf_flip_is_exact():
    for f, g, q in itertools.product((30.0, 100.0, 1000.0, 8000.0, 19000.0),
                                     (0.1, 3.0, 6.0, 12.0), (0.1, 0.7, 2.0, 10.0)):
        for kind in ("low_shelf", "high_shelf"):
            boost = FB(kind, f, g, q)
            cut = preamp.flip_shelf(boost)
            assert cut.type != kind and cut.gain == -g
            a = preamp.curve_db([boost], FREQS)
            b = preamp.curve_db([cut], FREQS)
            assert max(abs(x - (y + g)) for x, y in zip(a, b)) < 1e-6


def test_warm_bass_is_flipped_not_trimmed():
    result = preamp.compute(WARM_BASS)
    assert round(result.peak_db, 1) == 4.8 and result.peak_hz == 20.0
    assert result.method == "flip" and result.flipped == [1]
    assert result.bands[1] == FB("high_shelf", 100.0, -6.0, 0.7)
    assert [result.bands[i] for i in (0, 2, 3, 4)] == [WARM_BASS[i] for i in (0, 2, 3, 4)]
    assert result.preamp_db == -6.0
    assert round(result.device_peak_db, 1) == -1.2
    assert result.trim_index is None and result.warning is None


def test_compute_does_not_change_its_input():
    bands = list(WARM_BASS)
    preamp.compute(bands)
    assert bands == WARM_BASS and bands[1].type == "low_shelf"


def test_peak_boost_gets_a_trim_band_in_the_last_free_slot():
    result = preamp.compute(_with(b2=FB("peaking", 1000.0, 6.0, 1.0)))
    assert result.method == "trim" and result.trim_index == 4
    assert result.bands[4] == FB("high_shelf", 20.0, -6.5, 0.707)
    assert result.preamp_db == -6.5
    assert 0 >= result.device_peak_db > -1.0
    assert result.bands[2] == FB("peaking", 1000.0, 6.0, 1.0)


def test_only_the_shelves_needed_are_flipped():
    result = preamp.compute(_with(b0=FB("low_shelf", 100.0, 6.0, 0.7),
                                  b4=FB("high_shelf", 10000.0, 3.0, 0.71)))
    assert result.flipped == [0] and result.bands[4].gain == 3.0
    assert result.preamp_db == -6.0 and result.device_peak_db <= 0


def test_flip_then_trim():
    result = preamp.compute(_with(b0=FB("low_shelf", 100.0, 6.0, 0.7),
                                  b2=FB("peaking", 3000.0, 9.0, 1.0)))
    assert result.method == "flip+trim" and result.flipped == [0] and result.trim_index == 4
    assert result.preamp_db == -6.0 + result.bands[4].gain
    assert result.bands[4].gain % 0.5 == 0 and result.device_peak_db <= 0


def test_no_free_band_warns_and_changes_nothing():
    bands = [FB("peaking", f, 2.0, 1.0) for f in (100.0, 300.0, 1000.0, 3000.0, 8000.0)]
    result = preamp.compute(bands)
    assert result.warning == "no_free_band" and result.bands == bands
    assert result.preamp_db == 0.0 and result.device_peak_db > 0


def test_trim_stops_at_minus_12_db():
    result = preamp.compute(_with(b1=FB("peaking", 1000.0, 12.0, 1.0),
                                  b2=FB("peaking", 1000.0, 12.0, 1.0)))
    assert result.bands[4].gain == -12.0 and result.warning == "trim_limit"


def test_cuts_need_no_preamp():
    bands = [FB("peaking", 40.0, -1.5, 0.5), FB("peaking", 200.0, -6.0, 0.6)] + WARM_BASS[2:]
    result = preamp.compute(bands)
    assert result.method == "none" and result.preamp_db == 0.0 and result.bands == bands


def test_auto_off_only_reports_the_peak():
    result = preamp.compute(WARM_BASS, auto=False)
    assert result.method == "none" and result.bands == WARM_BASS
    assert round(result.peak_db, 1) == 4.8 and result.preamp_db == 0.0


def test_to_dict_is_rounded_for_the_ui():
    data = preamp.compute(WARM_BASS).to_dict()
    assert data == {"preamp_db": -6.0, "peak_db": 4.8, "peak_hz": 20, "device_peak_db": -1.2,
                    "method": "flip", "flipped": [1], "trim_index": None, "warning": None}
