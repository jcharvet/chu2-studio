"""ui/eqmath.js and ui/format.js; the JS curve must match chu2/eq.py.

    python -m pytest -q tests/ui/test_ui_eqmath.py
"""

import dataclasses

from chu2 import eq

FREQS = [20.0, 31.5, 63.0, 100.0, 250.0, 1000.0, 3150.0, 8000.0, 12500.0, 20000.0]
BANDS = [eq.FilterBand("peaking", 40.0, -1.5, 0.5), eq.FilterBand("low_shelf", 100.0, 6.0, 0.7),
         eq.FilterBand("peaking", 1400.0, -2.5, 1.6), eq.FilterBand("high_shelf", 9000.0, 3.0, 2.0),
         eq.FilterBand("peaking", 6000.0, 12.0, 10.0)]


def _js(page, script, arg=None):
    return page.evaluate("async (arg) => { const m = await import('./eqmath.js'); "
                         "const f = await import('./format.js'); " + script + " }", arg)


def test_js_curve_matches_eq_py(open_app):
    page = open_app()
    bands = [dict(dataclasses.asdict(b), bypass=False) for b in BANDS]
    js = _js(page, "return arg.freqs.map((x) => m.curveDb(arg.bands, x));",
             {"freqs": FREQS, "bands": bands})
    py = eq.Equalizer(BANDS).magnitude_response_db(FREQS)
    assert max(abs(a - b) for a, b in zip(js, py)) <= 0.01
    for band in BANDS:  # each filter type on its own
        one = [dict(dataclasses.asdict(band), bypass=False)]
        js = _js(page, "return arg.freqs.map((x) => m.curveDb(arg.bands, x));", {"freqs": FREQS, "bands": one})
        py = eq.Equalizer([band]).magnitude_response_db(FREQS)
        assert max(abs(a - b) for a, b in zip(js, py)) <= 0.01, band


def test_bypassed_bands_play_flat(open_app):
    page = open_app()
    flat = _js(page, "return m.curveDb([{type: 'peaking', frequency: 1000, gain: 6, q: 1, bypass: true}], 1000);")
    assert flat == 0


def test_quantize_clamps_to_the_chu2_limits(open_app):
    page = open_app()
    out = _js(page, """return [
        m.quantizeBand({type: 'peaking', frequency: 25000.4, gain: 13.26, q: 0.01}),
        m.quantizeBand({type: 'low_shelf', frequency: 3.2, gain: -12.9, q: 99, bypass: 1}),
        m.quantizeBand({type: 'peaking', frequency: 1000.49, gain: -0.04, q: 0.7071})];""")
    assert out == [
        {"type": "peaking", "frequency": 20000, "gain": 12, "q": 0.1, "bypass": False},
        {"type": "low_shelf", "frequency": 20, "gain": -12, "q": 10, "bypass": True},
        {"type": "peaking", "frequency": 1000, "gain": 0, "q": 0.707, "bypass": False},
    ]


def test_log_axis_round_trips(open_app):
    page = open_app()
    out = _js(page, """return [m.xOfFreq(20, 40, 690), m.xOfFreq(20000, 40, 690), m.xOfFreq(632.456, 40, 690),
        m.freqOfX(365, 40, 690), m.yOfGain(15, 10, 310, 15), m.yOfGain(-15, 10, 310, 15),
        m.gainOfY(160, 10, 310, 15), m.logFreqs(3)];""")
    assert out[0] == 40 and abs(out[1] - 690) < 1e-9 and abs(out[2] - 365) < 0.01
    assert abs(out[3] - 632.456) < 0.01 and out[4] == 10 and out[5] == 310 and out[6] == 0
    assert [round(f, 6) for f in out[7]] == [20, 632.455532, 20000]


def test_numbers_read_like_the_brief(open_app):
    page = open_app()
    out = _js(page, """return [f.formatFreq(105), f.formatFreq(1400), f.formatFreq(10000), f.formatFreq(12500),
        f.formatGain(3), f.formatGain(-2.5), f.formatGain(0), f.formatGain(-0.04), f.formatQ(0.707),
        f.chipText(1, {type: 'peaking', frequency: 250, gain: -2, q: 1}),
        f.describeBand(1, {type: 'peaking', frequency: 250, gain: -2, q: 1, bypass: false}),
        f.amount(-6), f.amount(-6.5), f.formatDate('2026-09-19T14:02:00')];""")
    assert out == ["105 Hz", "1.40 kHz", "10 kHz", "12.5 kHz",
                   "+3.0 dB", "−2.5 dB", "0.0 dB", "0.0 dB", "0.71",
                   "2 · Peak · 250 Hz · −2.0 dB · Q 1.00",
                   "Band 2, Peak, 250 hertz, minus 2.0 decibels, Q 1.00",
                   "6", "6.5", "19 Sep 2026, 14:02"]
