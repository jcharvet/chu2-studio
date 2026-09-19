"""Command-line interface for the Moondrop CHU 2 DSP tool.

The CLI is split into two halves:

* **Device commands** (``info``, ``probe``, ``test``, ``devices``, ``hid``) that
  require a connected device and pyusb/hidapi.
* **Offline commands** (``preset``, ``eq``) that work without hardware so
  presets can be authored, validated, and exported anywhere.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from . import __version__, device as device_mod, dsp, eq, preset


def _default_presets_dir() -> str:
    # Prefer ./presets relative to the current working directory.
    return os.environ.get("CHU2_PRESETS_DIR", os.path.join(os.getcwd(), "presets"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chu2",
        description="Open-source DSP control tool for the Moondrop CHU 2.",
    )
    parser.add_argument("--version", action="version", version=f"chu2-dsp {__version__}")
    parser.add_argument(
        "--presets-dir",
        default=_default_presets_dir(),
        help="directory scanned for EQ presets (default: ./presets)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- device commands -------------------------------------------------- #
    p_info = sub.add_parser("info", help="show CHU 2 descriptors")
    p_info.set_defaults(func=_cmd_info)

    p_probe = sub.add_parser("probe", help="run the safe DSP probe (interface 3 only)")
    p_probe.set_defaults(func=_cmd_probe)

    p_test = sub.add_parser(
        "test", help="brute-force candidate control-transfer commands (Phase 3)"
    )
    p_test.set_defaults(func=_cmd_test)

    p_devices = sub.add_parser("devices", help="list all connected USB devices")
    p_devices.set_defaults(func=_cmd_devices)

    p_hid = sub.add_parser("hid", help="list connected HID devices (hidapi)")
    p_hid.set_defaults(func=_cmd_hid)

    # ---- hardware DSP EQ commands ----------------------------------------- #
    p_dsp = sub.add_parser("dsp", help="read/write the EQ stored in the CHU 2 DSP")
    p_dsp_sub = p_dsp.add_subparsers(dest="dsp_command", required=True)

    p_dsp_read = p_dsp_sub.add_parser("read", help="show the EQ stored in the DSP")
    p_dsp_read.add_argument("--save", "-o", help="also save it as a preset JSON file")
    p_dsp_read.set_defaults(func=_cmd_dsp_read)

    p_dsp_write = p_dsp_sub.add_parser("write", help="write a preset to the DSP and save it")
    p_dsp_write.add_argument("name", help="preset file path or name")
    p_dsp_write.add_argument("--no-commit", action="store_true",
                             help="write and verify, but do not save to the DSP's memory")
    p_dsp_write.set_defaults(func=_cmd_dsp_write)

    p_dsp_restore = p_dsp_sub.add_parser(
        "restore", help="write back the EQ backed up before the first 'dsp write'"
    )
    p_dsp_restore.set_defaults(func=_cmd_dsp_restore)

    # ---- Equalizer APO commands ------------------------------------------- #
    p_apo = sub.add_parser("apo", help="write presets directly to Equalizer APO")
    p_apo_sub = p_apo.add_subparsers(dest="apo_command", required=True)

    p_apo_apply = p_apo_sub.add_parser("apply", help="write a preset to APO config.txt")
    p_apo_apply.add_argument("name", help="preset file path or name")
    p_apo_apply.add_argument("--config-path", help="explicit config.txt path (auto-detected if omitted)")
    p_apo_apply.add_argument("--no-backup", action="store_true", help="skip making a .bak backup")
    p_apo_apply.set_defaults(func=_cmd_apo_apply)

    p_apo_detect = p_apo_sub.add_parser("detect", help="show the detected APO config path")
    p_apo_detect.set_defaults(func=_cmd_apo_detect)

    p_apo_restore = p_apo_sub.add_parser("restore", help="restore config.txt from its .bak backup")
    p_apo_restore.add_argument("--config-path", help="explicit config.txt path")
    p_apo_restore.set_defaults(func=_cmd_apo_restore)

    # ---- preset commands -------------------------------------------------- #
    p_preset = sub.add_parser("preset", help="manage EQ presets")
    p_sub = p_preset.add_subparsers(dest="preset_command", required=True)

    p_list = p_sub.add_parser("list", help="list available presets")
    p_list.set_defaults(func=_cmd_preset_list)

    p_show = p_sub.add_parser("show", help="show a preset and its coefficients")
    p_show.add_argument("name", help="preset file path or name")
    p_show.set_defaults(func=_cmd_preset_show)

    p_validate = p_sub.add_parser("validate", help="validate a preset JSON file")
    p_validate.add_argument("file", help="path to a preset JSON file")
    p_validate.set_defaults(func=_cmd_preset_validate)

    p_export = p_sub.add_parser("export", help="export a preset to another format")
    p_export.add_argument("name", help="preset file path or name")
    p_export.add_argument(
        "--format",
        choices=["json", "equalizerapo", "coefficients"],
        default="equalizerapo",
        help="output format",
    )
    p_export.add_argument("--out", "-o", help="output file (default: stdout)")
    p_export.set_defaults(func=_cmd_preset_export)

    p_new = p_sub.add_parser("new", help="write a neutral template preset")
    p_new.add_argument("--name", default="Default (Flat)", help="preset name")
    p_new.add_argument("--out", "-o", required=True, help="output JSON file")
    p_new.set_defaults(func=_cmd_preset_new)

    p_import = p_sub.add_parser("import", help="convert an EqualizerAPO .txt into a preset")
    p_import.add_argument("file", help="EqualizerAPO/Peace/AutoEQ config .txt")
    p_import.add_argument("--name", help="preset name (default: derived from filename)")
    p_import.add_argument("--out", "-o", help="output JSON file (default: presets dir)")
    p_import.set_defaults(func=_cmd_preset_import)

    # ---- EQ math commands ------------------------------------------------- #
    p_eq = sub.add_parser("eq", help="offline EQ math and preview")
    p_eq_sub = p_eq.add_subparsers(dest="eq_command", required=True)

    p_biquad = p_eq_sub.add_parser("biquad", help="compute biquad coefficients for a band")
    p_biquad.add_argument("--type", default="peaking", choices=eq.FILTER_TYPES)
    p_biquad.add_argument("--freq", type=float, default=1000.0)
    p_biquad.add_argument("--gain", type=float, default=0.0)
    p_biquad.add_argument("--q", type=float, default=1.0)
    p_biquad.add_argument("--sample-rate", type=int, default=eq.DEFAULT_SAMPLE_RATE)
    p_biquad.set_defaults(func=_cmd_eq_biquad)

    p_response = p_eq_sub.add_parser(
        "response", help="print the composite magnitude response of a preset"
    )
    p_response.add_argument("name", help="preset file path or name")
    p_response.add_argument("--min", type=float, default=20.0, dest="fmin")
    p_response.add_argument("--max", type=float, default=20000.0, dest="fmax")
    p_response.add_argument("--points", type=int, default=128)
    p_response.set_defaults(func=_cmd_eq_response)

    return parser


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _resolve_preset(name: str, presets_dir: str) -> str:
    """Resolve a preset name to a file path (exact path or name under dir)."""
    if os.path.isfile(name):
        return name
    candidate = os.path.join(presets_dir, name)
    if os.path.isfile(candidate):
        return candidate
    if not name.lower().endswith(".json"):
        candidate_json = candidate + ".json"
        if os.path.isfile(candidate_json):
            return candidate_json
    raise preset.PresetError(
        f"preset not found: {name} (searched {presets_dir} and the working directory)"
    )


def _print(text: str) -> None:
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def _print_bands(bands: Sequence[eq.FilterBand]) -> None:
    _print(f"{'type':<12} {'freq (Hz)':>12} {'gain (dB)':>12} {'Q':>8}")
    for band in bands:
        _print(f"{band.type:<12} {band.frequency:>12.1f} {band.gain:>12.1f} {band.q:>8.3f}")


# --------------------------------------------------------------------------- #
# Device commands
# --------------------------------------------------------------------------- #
def _cmd_info(args: argparse.Namespace) -> int:
    dev = device_mod.require_chu2()
    _print(device_mod.format_device_report(dev))
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    from . import research  # pyusb research tools, not part of the app

    with research.DspTransport.open() as transport:
        results = research.probe(transport)
    _print(research.format_probe_results(results))
    _print("\nAudio should still work — only Interface 3 was touched.")
    return 0 if all(r.ok for r in results) else 2


def _cmd_test(args: argparse.Namespace) -> int:
    from . import research  # pyusb research tools, not part of the app

    with research.DspTransport.open() as transport:
        results = research.test_commands(transport)
    _print(research.format_command_results(results))
    return 0 if all(r.ok for r in results) else 2


def _cmd_devices(args: argparse.Namespace) -> int:
    for info in device_mod.enumerate_devices():
        line = str(info)
        if info.known_product:
            line += "   <-- recognized DSP device"
        _print(line)
    return 0


def _cmd_hid(args: argparse.Namespace) -> int:
    for info in device_mod.list_hid_devices():
        _print(
            f"{info.get('vendor_id', 0):04X}:{info.get('product_id', 0):04X} "
            f"{info.get('product_string') or '(no product string)'} "
            f"interface={info.get('interface_number', '?')}"
        )
    return 0


# --------------------------------------------------------------------------- #
# Hardware DSP EQ commands
# --------------------------------------------------------------------------- #
def _dsp_backup_path(args: argparse.Namespace) -> str:
    return os.path.join(args.presets_dir, "chu2_hardware_backup.json")


def _cmd_dsp_read(args: argparse.Namespace) -> int:
    with dsp.HidTransport.open() as transport:
        slot, bands = dsp.kt_read_eq(transport)
    state = {dsp.KT_SLOT_ON: "on", dsp.KT_SLOT_OFF: "off"}.get(slot, "unknown")
    _print(f"EQ slot: 0x{slot:02X} ({state})")
    _print_bands(bands)
    if args.save:
        preset.save(preset.Preset(name="CHU 2 hardware EQ", bands=bands), args.save)
        _print(f"Saved {args.save}")
    return 0


def _cmd_dsp_write(args: argparse.Namespace) -> int:
    data = preset.load(_resolve_preset(args.name, args.presets_dir))
    bands = dsp.kt_fit_bands(data.bands)  # reject a bad preset before touching the DSP
    if data.preamp:
        _print(f"note: the DSP has no preamp, so Preamp {data.preamp:+.1f} dB is ignored. "
               "Lower the volume if boosts clip.")

    with dsp.HidTransport.open() as transport:
        backup = _dsp_backup_path(args)
        # ponytail: the backup is written once and never overwritten, so
        # 'dsp restore' always returns to the EQ found before the first write.
        if not os.path.isfile(backup):
            _slot, current = dsp.kt_read_eq(transport)
            preset.save(
                preset.Preset(
                    name="CHU 2 hardware EQ (backup)",
                    description="DSP EQ found before the first 'chu2 dsp write'.",
                    bands=current,
                ),
                backup,
            )
            _print(f"Backed up the current DSP EQ to {backup}")
        dsp.kt_write_eq(transport, bands, commit=not args.no_commit)

    _print_bands(bands)
    saved = "not saved (--no-commit)" if args.no_commit else "saved"
    _print(f"Wrote '{data.name}' to the DSP: verified by read-back, {saved}.")
    if not args.no_commit:
        _print(_RESTART_NOTE)
    return 0


_RESTART_NOTE = ("The CHU 2 restarts to save: audio stops for a moment. "
                 "Wait a few seconds before the next command.")


def _cmd_dsp_restore(args: argparse.Namespace) -> int:
    backup = _dsp_backup_path(args)
    if not os.path.isfile(backup):
        _print(f"No backup at {backup}. It is made by the first 'chu2 dsp write'.")
        return 1
    data = preset.load(backup)
    with dsp.HidTransport.open() as transport:
        dsp.kt_write_eq(transport, data.bands)
    _print_bands(data.bands)
    _print(f"Restored the DSP EQ from {backup}: verified by read-back, saved.")
    _print(_RESTART_NOTE)
    return 0


# --------------------------------------------------------------------------- #
# Equalizer APO commands
# --------------------------------------------------------------------------- #
#: File our EQ is written to; config.txt is pointed at it (like Peace's peace.txt).
_APO_FILE = "chu2studio.txt"


def _apo_config_dir() -> str:
    """Return the Equalizer APO ``config`` directory, or raise."""
    candidates = []
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.append(os.path.join(base, "EqualizerAPO", "config"))

    # Also consult the Windows uninstall registry for the real install dir.
    try:
        import winreg
    except ImportError:
        winreg = None
    if winreg is not None:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for uninst in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ):
                try:
                    key = winreg.OpenKey(hive, uninst)
                except OSError:
                    continue
                with key:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(key, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            with winreg.OpenKey(key, sub) as sk:
                                name, _ = winreg.QueryValueEx(sk, "DisplayName")
                                if "Equalizer APO" in name:
                                    uninst_str, _ = winreg.QueryValueEx(sk, "UninstallString")
                                    install_dir = os.path.dirname(uninst_str.strip('"'))
                                    candidates.append(os.path.join(install_dir, "config"))
                        except OSError:
                            pass

    for d in candidates:
        if os.path.isfile(os.path.join(d, "config.txt")):
            return d
    raise preset.PresetError(
        "Equalizer APO config directory not found.\n"
        "Install Equalizer APO, or pass --config-path <path> explicitly."
    )


def _find_apo_config() -> str:
    """Return the Equalizer APO config.txt path."""
    return os.path.join(_apo_config_dir(), "config.txt")


def _extract_device_scope(config_path: str):
    """Return the Device:/Channel: lines that scope the current EQ.

    They sit either in config.txt itself (``Device: Chu2 DSP`` then
    ``Include: x.txt``) or in the file it includes (Peace writes them into
    peace.txt). We carry them over so our EQ applies to the CHU 2 only, not
    every device on the machine.
    """
    def read_lines(path: str) -> List[str]:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read().splitlines()
        except OSError:
            return []

    def scope_of(lines: List[str]) -> List[str]:
        return [l for l in lines if l.strip().startswith(("Device:", "Channel:"))]

    lines = read_lines(config_path)
    scope = scope_of(lines)
    for line in lines:
        line = line.strip()
        if line.lower().startswith("include:"):
            inc_name = line.split(":", 1)[1].strip().strip('"')
            scope += scope_of(read_lines(os.path.join(os.path.dirname(config_path), inc_name)))
            break
    return scope


def _cmd_apo_apply(args: argparse.Namespace) -> int:
    path = _resolve_preset(args.name, args.presets_dir)
    data = preset.load(path)

    if args.config_path:
        config_path = args.config_path
        config_dir = os.path.dirname(os.path.abspath(config_path))
    else:
        config_dir = _apo_config_dir()
        config_path = os.path.join(config_dir, "config.txt")

    scope = _extract_device_scope(config_path)
    body = preset.to_equalizer_apo(data).rstrip("\n")
    output = "\n".join(scope + [body]) + "\n"

    # Write our EQ to a dedicated file, then point config.txt at it (like Peace
    # writes peace.txt and config.txt includes it).
    out_file = os.path.join(config_dir, _APO_FILE)
    os.makedirs(config_dir, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as handle:
        handle.write(output)

    if not args.no_backup:
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                original = handle.read()
        except FileNotFoundError:
            original = ""
        # Back up only a config this tool did not write; otherwise a second
        # apply overwrites the real backup with our own Include line.
        if original and _APO_FILE not in original:
            with open(config_path + ".bak", "w", encoding="utf-8") as handle:
                handle.write(original)

    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write(f"Include: {_APO_FILE}\n")

    _print(f"Wrote '{data.name}' to {out_file}")
    _print(f"Updated {config_path} to include it.")
    _print("Equalizer APO applies it immediately (no restart needed).")
    return 0


def _cmd_apo_detect(args: argparse.Namespace) -> int:
    try:
        _print(_find_apo_config())
    except preset.PresetError as exc:
        _print(str(exc))
        return 1
    return 0


def _cmd_apo_restore(args: argparse.Namespace) -> int:
    config_path = args.config_path or _find_apo_config()
    backup = config_path + ".bak"
    if not os.path.isfile(backup):
        _print(f"No backup found at {backup}")
        return 1
    with open(backup, "r", encoding="utf-8") as handle:
        original = handle.read()
    with open(config_path, "w", encoding="utf-8") as handle:
        handle.write(original)
    _print(f"Restored {config_path} from backup.")
    return 0


# --------------------------------------------------------------------------- #
# Preset commands
# --------------------------------------------------------------------------- #
def _cmd_preset_list(args: argparse.Namespace) -> int:
    paths = preset.discover(args.presets_dir)
    if not paths:
        _print(f"No presets found under {args.presets_dir}")
        return 0
    for path in paths:
        rel = os.path.relpath(path, args.presets_dir)
        _print(rel)
    return 0


def _cmd_preset_show(args: argparse.Namespace) -> int:
    path = _resolve_preset(args.name, args.presets_dir)
    data = preset.load(path)
    _print(f"name        : {data.name}")
    _print(f"description : {data.description or '(none)'}")
    _print(f"sample_rate : {data.sample_rate} Hz")
    _print(f"bands       : {len(data.bands)}")
    _print_bands(data.bands)
    return 0


def _cmd_preset_validate(args: argparse.Namespace) -> int:
    errors = preset.validate(_read_json(args.file))
    if errors:
        _print("Invalid preset:")
        for error in errors:
            _print(f"  - {error}")
        return 1
    _print("Preset is valid.")
    return 0


def _cmd_preset_export(args: argparse.Namespace) -> int:
    path = _resolve_preset(args.name, args.presets_dir)
    data = preset.load(path)
    if args.format == "json":
        output = data.to_json()
    elif args.format == "equalizerapo":
        output = preset.to_equalizer_apo(data)
    else:
        output = preset.to_coefficients_csv(data)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(output)
        _print(f"Wrote {args.out}")
    else:
        _print(output)
    return 0


def _cmd_preset_new(args: argparse.Namespace) -> int:
    data = preset.flat_preset(name=args.name)
    preset.save(data, args.out)
    _print(f"Wrote {args.out}")
    return 0


def _cmd_preset_import(args: argparse.Namespace) -> int:
    try:
        with open(args.file, "r", encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    name = args.name
    if not name:
        name = os.path.splitext(os.path.basename(args.file))[0].replace("_", " ").replace("-", " ").title()
    data = preset.from_equalizer_apo(text, name=name)

    if not data.bands:
        _print("No filters found in that file.")
        return 1

    if args.out:
        out = args.out
    else:
        safe = name.lower().replace(" ", "_")
        out = os.path.join(args.presets_dir, safe + ".json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    preset.save(data, out)
    _print(f"Imported {len(data.bands)} bands -> {out}")
    _print(f"Apply with: chu2 apo apply {os.path.splitext(os.path.basename(out))[0]}")
    return 0


# --------------------------------------------------------------------------- #
# EQ commands
# --------------------------------------------------------------------------- #
def _cmd_eq_biquad(args: argparse.Namespace) -> int:
    band = eq.FilterBand(
        type=args.type, frequency=args.freq, gain=args.gain, q=args.q
    )
    biquad = eq.band_coefficients(band, args.sample_rate)
    _print(f"type={band.type} f={band.frequency:.1f} Hz gain={band.gain:.1f} dB q={band.q:.3f}")
    _print(
        f"b0={biquad.b0:.10f} b1={biquad.b1:.10f} b2={biquad.b2:.10f} "
        f"a1={biquad.a1:.10f} a2={biquad.a2:.10f}"
    )
    return 0


def _cmd_eq_response(args: argparse.Namespace) -> int:
    path = _resolve_preset(args.name, args.presets_dir)
    data = preset.load(path)
    freqs = eq.log_frequency_axis(args.fmin, args.fmax, args.points)
    response = data.equalizer().magnitude_response_db(freqs)
    _print("frequency_hz,gain_db")
    for f, g in zip(freqs, response):
        _print(f"{f:.3f},{g:.4f}")
    return 0


def _read_json(path: str):
    import json

    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (device_mod.UsbError, preset.PresetError, ValueError, OSError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
