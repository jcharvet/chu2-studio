"""Share codes (brief S7): CHU2-1.<name>.<payload>.<CRC-16>.

    python -m pytest -q tests/test_sharecode.py
"""

from chu2 import eq, sharecode

FB = eq.FilterBand
NIGHT_DRIVE = [FB("low_shelf", 80.0, 3.5, 0.71), FB("peaking", 250.0, -2.0, 1.0),
               FB("peaking", 1000.0, 0.0, 1.0), FB("peaking", 6400.0, 12.0, 10.0),
               FB("high_shelf", 20000.0, -12.0, 0.1)]


def _raises(func) -> str:
    try:
        func()
    except sharecode.ShareCodeError as exc:
        return str(exc)
    raise AssertionError("no ShareCodeError")


def test_round_trip_keeps_every_band_and_the_name():
    code = sharecode.encode("Night Drive", NIGHT_DRIVE)
    assert code.startswith("CHU2-1.NightDrive.") and len(code) < 70
    name, bands = sharecode.decode(code)
    assert name == "NightDrive" and bands == NIGHT_DRIVE


def test_values_are_rounded_to_device_steps():
    _name, bands = sharecode.decode(sharecode.encode("x", [FB("peaking", 1234.4, -2.04, 0.7071)]))
    assert bands[0] == FB("peaking", 1234.0, -2.0, 0.707)
    assert bands[1:] == [FB("peaking", 1000.0, 0.0, 1.0)] * 4  # missing bands are flat


def test_a_typo_is_caught_by_the_check_digits():
    code = sharecode.encode("Night Drive", NIGHT_DRIVE)
    head, payload, crc = code.rsplit(".", 2)
    broken = f"{head}.{('B' if payload[3] != 'B' else 'C').join([payload[:3], payload[4:]])}.{crc}"
    assert "check" in _raises(lambda: sharecode.decode(broken))


def test_a_newer_version_is_refused_politely():
    assert "newer" in _raises(lambda: sharecode.decode("CHU2-9.Name.AAAA.0000"))


def test_not_a_code():
    assert "not a CHU 2 Studio share code" in _raises(lambda: sharecode.decode("hello"))


def test_find_a_code_in_pasted_text():
    code = sharecode.encode("Night Drive", NIGHT_DRIVE)
    wrapped = f"Here is my EQ:\n  {code[:30]}\n{code[30:]}  \nenjoy!"
    assert sharecode.find_code(wrapped) == code
    assert sharecode.find_code("Filter 1: ON PK Fc 100 Hz Gain 3 dB Q 1") is None


def test_safe_names():
    assert sharecode.safe_name("Night Drive!") == "NightDrive"
    assert sharecode.safe_name("warm_bass-2") == "Warm_bass-2"
    assert sharecode.safe_name("   ") == "EQ"
    assert len(sharecode.safe_name("x" * 80)) == 32


def test_describe_as_text():
    assert sharecode.describe(NIGHT_DRIVE[:2]) == (
        "LS 80 Hz +3.5 Q0.71 · PK 250 Hz −2.0 Q1.00")
    assert sharecode.describe([FB("peaking", 1000.0, 0.0, 1.0)]) == "Flat (all bands at 0 dB)"


def test_a_huge_version_number_is_not_a_code():
    code = "CHU2-" + "9" * 5000 + ".Name.AAAA.0000"  # int() refuses > 4300 digits
    assert "not a CHU 2 Studio share code" in _raises(lambda: sharecode.decode(code))
    assert sharecode.find_code("try " + code) is None
