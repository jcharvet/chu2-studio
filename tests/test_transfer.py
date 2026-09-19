"""Import and export (brief S7): EQ text files, .chu2.json, share codes.

    python -m pytest -q tests/test_transfer.py
"""

import json

from chu2 import eq, preset, sharecode, transfer

AUTOEQ = """Preamp: -6.2 dB
Filter 1: ON LSC Fc 105 Hz Gain 6.5 dB Q 0.70
Filter 2: ON PK Fc 180 Hz Gain -3.1 dB Q 1.20
Filter 3: ON PK Fc 680 Hz Gain 1.8 dB Q 1.77
Filter 4: ON PK Fc 2400 Hz Gain -0.4 dB Q 2.00
Filter 5: ON PK Fc 3500 Hz Gain -2.2 dB Q 1.40
Filter 6: ON PK Fc 6416 Hz Gain 5.7 dB Q 2.89
Filter 7: ON PK Fc 8120 Hz Gain 13.0 dB Q 4.10
Filter 8: ON HSC Fc 10000 Hz Gain -0.8 dB Q 0.70
Filter 9: ON HP Fc 20 Hz Q 0.71
Filter 10: OFF PK Fc 500 Hz Gain 9.0 dB Q 1.00
"""


def test_an_autoeq_file_keeps_the_five_largest_filters():
    got = transfer.read_text(AUTOEQ, "ParametricEQ.txt")
    assert got["name"] == "ParametricEQ" and got["format"] == "Equalizer APO / AutoEq text"
    assert got["total"] == 9 and got["preamp"] == -6.2  # the OFF filter is not heard, so not counted
    kept = [(b["type"], b["frequency"], b["gain"]) for b in got["bands"]]
    assert kept == [("low_shelf", 105.0, 6.5), ("peaking", 180.0, -3.1), ("peaking", 3500.0, -2.2),
                    ("peaking", 6416.0, 5.7), ("peaking", 8120.0, 12.0)]  # 5 largest, file order
    status = {row["n"]: row["status"] for row in got["filters"]}
    assert status[7] == "gain limited to +12.0" and status[9] == "high-pass isn't available on CHU 2"
    assert status[3] == "not kept (5 bands)" and status[1] == "fits"
    assert got["notes"] == [
        "CHU 2 has 5 bands. This file has 9: keeping the 5 largest.",
        "The file's preamp (−6.2 dB) isn't copied: CHU 2 Studio works out its own preamp "
        "from the bands."]


def test_a_short_file_is_padded_with_idle_bands():
    got = transfer.read_text("Filter: ON PK Fc 1000 Hz Gain -3 dB Q 1.0\n", "one.txt")
    assert got["bands"][0]["gain"] == -3.0 and [b["gain"] for b in got["bands"][1:]] == [0.0] * 4
    assert got["notes"] == []


def test_a_share_code_in_pasted_text():
    code = sharecode.encode("Night Drive", [eq.FilterBand("low_shelf", 80.0, 3.5, 0.71)])
    got = transfer.read_text(f"try this: {code}")
    assert got["format"] == "Share code" and got["name"] == "NightDrive"
    assert got["bands"][0]["gain"] == 3.5


def test_copy_as_text_pastes_back():
    bands = [eq.FilterBand("peaking", 166.0, -2.6, 0.87), eq.FilterBand("peaking", 5928.0, 6.7, 0.95),
             eq.FilterBand("peaking", 1000.0, 0.0, 1.0), eq.FilterBand("low_shelf", 80.0, 3.5, 0.71),
             eq.FilterBand("high_shelf", 10000.0, -3.1, 0.7)]
    got = transfer.read_text(sharecode.describe(bands))  # "PK 166 Hz −2.6 Q0.87 · PK 5.93 kHz +6.7 …"
    assert got["format"] == "CHU 2 Studio text"
    assert [(b["type"], b["frequency"], b["gain"], b["q"]) for b in got["bands"]] == [
        ("peaking", 166.0, -2.6, 0.87), ("peaking", 5930.0, 6.7, 0.95), ("low_shelf", 80.0, 3.5, 0.71),
        ("high_shelf", 10000.0, -3.1, 0.7), ("high_shelf", 10000.0, 0.0, 0.71)]  # 0 dB band: idle slot


def test_a_chu2_json_preset():
    text = json.dumps({"version": 1, "name": "Mine", "bands": [
        {"type": "high_shelf", "frequency": 8000, "gain": -2, "q": 0.7, "bypass": True}]})
    got = transfer.read_text(text, "mine.chu2.json")
    assert got["format"] == "CHU 2 Studio preset" and got["name"] == "Mine"
    assert got["bands"][0] == {"type": "high_shelf", "frequency": 8000.0, "gain": -2.0, "q": 0.7,
                               "bypass": True}


def test_text_without_filters_is_refused():
    try:
        transfer.read_text("hello there")
    except transfer.TransferError as exc:
        assert "No EQ filters" in str(exc)
        return
    raise AssertionError("no TransferError")


def test_export_apo_text_round_trips_and_carries_the_preamp():
    design = transfer.read_text(AUTOEQ)["bands"]
    design[1]["bypass"] = True
    text = transfer.export_apo("Warm", design, -6.0)
    assert text.splitlines()[:3] == ["# Warm", "# Exported from CHU 2 Studio. On the CHU 2 the "
                                     "preamp is built into the bands.", "Preamp: -6.0 dB"]
    assert "Filter 2: OFF PK Fc 180 Hz Gain -3.1 dB Q 1.200" in text
    again = transfer.read_text(text)
    assert again["bands"][0] == design[0] and again["preamp"] == -6.0


def test_export_json_is_a_chu2_preset(tmp_path):
    design = transfer.read_text(AUTOEQ)["bands"]
    path = tmp_path / "warm.chu2.json"
    path.write_text(transfer.export_json("Warm", design), encoding="utf-8")
    assert preset.load(str(path)).bands[0] == eq.FilterBand("low_shelf", 105.0, 6.5, 0.7)


def test_a_garbled_number_skips_its_line():
    text = ("Preamp: -.. dB\n"
            "Filter 1: ON PK Fc 1..2 Hz Gain 3.0 dB Q 1.0\n"
            "Filter 2: ON PK Fc 1000 Hz Gain 2.0 dB Q 1.0\n")
    preview = transfer.read_text(text)
    assert preview["total"] == 1 and preview["preamp"] is None
    assert preview["bands"][0]["frequency"] == 1000.0
    try:
        transfer.read_text("Filter 1: ON PK Fc . Hz Gain 3.0 dB Q 1.0")
    except transfer.TransferError as exc:
        assert "No EQ filters" in str(exc)
        return
    raise AssertionError("no TransferError")
