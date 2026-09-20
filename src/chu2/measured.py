"""The measured tunings published for the Moondrop Chu 2 (brief S6, group "measured").

Six people measured the Chu 2 and AutoEq turned each measurement into a filter set
that corrects it towards a target. Their text is kept here verbatim, and read with
the ordinary importer (:mod:`chu2.transfer`), so the ten filters are reduced to the
CHU 2's five by the same code a user's own file goes through, and the shortfall it
reports is what the preset card shows. Nothing is downloaded: the app makes no
network calls.

Source: https://github.com/jaakkopasanen/AutoEq, MIT licence, Copyright (c)
2018-2022 Jaakko Pasanen, fetched 2026-09-20. The measurements behind each set
belong to the person named in it; AutoEq states no separate terms for them.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import transfer

TUNINGS = (
    {
        "id": "crinacle-711",
        "name": "crinacle (711)",
        "by": "crinacle",
        "rig": "an IEC 60318-4 (711) coupler",
        "text": """\nPreamp: -3.7 dB
Filter 1: ON LSC Fc 105 Hz Gain -0.2 dB Q 0.70
Filter 2: ON PK Fc 166 Hz Gain -2.6 dB Q 0.87
Filter 3: ON PK Fc 5928 Hz Gain 6.7 dB Q 0.95
Filter 4: ON PK Fc 780 Hz Gain 2.2 dB Q 1.24
Filter 5: ON PK Fc 4221 Hz Gain -4.4 dB Q 0.80
Filter 6: ON HSC Fc 10000 Hz Gain -3.1 dB Q 0.70
Filter 7: ON PK Fc 9560 Hz Gain 1.6 dB Q 2.29
Filter 8: ON PK Fc 1418 Hz Gain -0.7 dB Q 2.98
Filter 9: ON PK Fc 1028 Hz Gain 0.5 dB Q 3.66
Filter 10: ON PK Fc 2167 Hz Gain 0.4 dB Q 4.09
""",
    },
    {
        "id": "crinacle-bk4620",
        "name": "crinacle (B&K 4620)",
        "by": "crinacle",
        "rig": "a Bruel & Kjaer 4620",
        "text": """\nPreamp: -2.5 dB
Filter 1: ON LSC Fc 105 Hz Gain -5.8 dB Q 0.70
Filter 2: ON PK Fc 520 Hz Gain 2.6 dB Q 0.80
Filter 3: ON PK Fc 181 Hz Gain -3.0 dB Q 1.70
Filter 4: ON PK Fc 3643 Hz Gain -1.9 dB Q 0.94
Filter 5: ON PK Fc 61 Hz Gain 3.7 dB Q 0.61
Filter 6: ON HSC Fc 10000 Hz Gain 1.4 dB Q 0.70
Filter 7: ON PK Fc 1407 Hz Gain -0.3 dB Q 2.12
Filter 8: ON PK Fc 6066 Hz Gain 0.6 dB Q 5.30
Filter 9: ON PK Fc 4760 Hz Gain -0.5 dB Q 4.78
Filter 10: ON PK Fc 855 Hz Gain 0.3 dB Q 2.97
""",
    },
    {
        "id": "hypethesonics",
        "name": "HypetheSonics (GRAS RA0045)",
        "by": "HypetheSonics",
        "rig": "a GRAS RA0045",
        "text": """\nPreamp: -5.2 dB
Filter 1: ON LSC Fc 105 Hz Gain -1.0 dB Q 0.70
Filter 2: ON PK Fc 6256 Hz Gain 5.6 dB Q 2.08
Filter 3: ON PK Fc 173 Hz Gain -2.2 dB Q 1.20
Filter 4: ON PK Fc 688 Hz Gain 1.8 dB Q 1.36
Filter 5: ON PK Fc 3259 Hz Gain -2.5 dB Q 1.67
Filter 6: ON HSC Fc 10000 Hz Gain -2.3 dB Q 0.70
Filter 7: ON PK Fc 68 Hz Gain 0.6 dB Q 1.76
Filter 8: ON PK Fc 114 Hz Gain -0.4 dB Q 2.53
Filter 9: ON PK Fc 1379 Hz Gain -0.2 dB Q 2.48
Filter 10: ON PK Fc 8425 Hz Gain 1.2 dB Q 5.63
""",
    },
    {
        "id": "kazi",
        "name": "Kazi",
        "by": "Kazi",
        "rig": "an in-ear rig",
        "text": """\nPreamp: -2.5 dB
Filter 1: ON LSC Fc 105 Hz Gain -3.4 dB Q 0.70
Filter 2: ON PK Fc 163 Hz Gain -2.9 dB Q 0.72
Filter 3: ON PK Fc 720 Hz Gain 2.0 dB Q 0.83
Filter 4: ON PK Fc 5976 Hz Gain 2.5 dB Q 2.12
Filter 5: ON PK Fc 70 Hz Gain 2.6 dB Q 0.92
Filter 6: ON HSC Fc 10000 Hz Gain -1.6 dB Q 0.70
Filter 7: ON PK Fc 3092 Hz Gain -1.1 dB Q 3.10
Filter 8: ON PK Fc 2109 Hz Gain 0.9 dB Q 2.85
Filter 9: ON PK Fc 8586 Hz Gain 1.5 dB Q 5.11
Filter 10: ON PK Fc 1249 Hz Gain -0.3 dB Q 3.47
""",
    },
    {
        "id": "super-review",
        "name": "Super Review",
        "by": "Super Review",
        "rig": "an in-ear rig",
        "text": """\nPreamp: -2.5 dB
Filter 1: ON LSC Fc 105 Hz Gain -4.1 dB Q 0.70
Filter 2: ON PK Fc 173 Hz Gain -3.7 dB Q 0.65
Filter 3: ON PK Fc 773 Hz Gain 2.2 dB Q 0.54
Filter 4: ON PK Fc 6178 Hz Gain 2.7 dB Q 3.65
Filter 5: ON PK Fc 69 Hz Gain 2.4 dB Q 0.75
Filter 6: ON HSC Fc 10000 Hz Gain -2.4 dB Q 0.70
Filter 7: ON PK Fc 2276 Hz Gain 0.8 dB Q 2.51
Filter 8: ON PK Fc 1315 Hz Gain -0.7 dB Q 2.48
Filter 9: ON PK Fc 865 Hz Gain 0.4 dB Q 2.45
Filter 10: ON PK Fc 3830 Hz Gain -0.4 dB Q 2.83
""",
    },
    {
        "id": "tonedeafmonk",
        "name": "ToneDeafMonk",
        "by": "ToneDeafMonk",
        "rig": "an in-ear rig",
        "text": """\nPreamp: -4.8 dB
Filter 1: ON LSC Fc 105 Hz Gain -1.4 dB Q 0.70
Filter 2: ON PK Fc 179 Hz Gain -2.9 dB Q 0.96
Filter 3: ON PK Fc 754 Hz Gain 1.9 dB Q 0.79
Filter 4: ON PK Fc 6280 Hz Gain 5.1 dB Q 3.63
Filter 5: ON PK Fc 3867 Hz Gain -1.4 dB Q 2.14
Filter 6: ON HSC Fc 10000 Hz Gain -1.2 dB Q 0.70
Filter 7: ON PK Fc 66 Hz Gain 0.5 dB Q 1.66
Filter 8: ON PK Fc 2126 Hz Gain 0.5 dB Q 2.80
Filter 9: ON PK Fc 115 Hz Gain -0.4 dB Q 2.49
Filter 10: ON PK Fc 26 Hz Gain -0.4 dB Q 2.54
""",
    },
)


def catalog() -> List[Dict[str, Any]]:
    """One preset item per tuning, in the shape :mod:`chu2.library` lists."""
    items = []
    for tuning in TUNINGS:
        preview = transfer.read_text(tuning["text"])
        items.append({
            "id": "measured:" + tuning["id"],
            "name": tuning["name"],
            "group": "measured",
            "tags": ["Measured", tuning["by"]],
            "bands": preview["bands"],
            "about": (f"AutoEq's correction for the Chu 2, measured by {tuning['by']} on "
                      f"{tuning['rig']}. Its {preview['total']} filters are reduced to the "
                      f"CHU 2's 5, within {preview['gap_db']:.1f} dB of the original."),
        })
    return items
