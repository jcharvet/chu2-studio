# API Reference

The Python package lives under `src/chu2/`. Everything is importable after
installing the project (`pip install -e .`) or by adding `src/` to `sys.path`.

```python
from chu2 import device, dsp, eq, preset
```

---

## `chu2.device` — discovery & descriptors

| Constant | Value | Meaning |
|----------|-------|---------|
| `MOONDROP_VID` | `0x31B2` | Moondrop vendor ID |
| `CHU2_DSP_PID` | `0x0113` | CHU 2 (DSP) product ID |
| `DSP_INTERFACE` | `3` | DSP control interface |
| `DSP_EP_OUT` | `0x03` | Host → DSP endpoint |
| `DSP_EP_IN` | `0x83` | DSP → Host endpoint |

### Functions

```python
find_chu2() -> Optional[usb.core.Device]
require_chu2() -> usb.core.Device      # raises UsbError if absent
enumerate_devices() -> list[DeviceInfo]
list_hid_devices() -> list[dict]       # hidapi
inspect_device(dev) -> list[ConfigurationInfo]
find_interface_endpoints(dev, interface_number) -> list[EndpointInfo]
format_device_report(dev) -> str       # human-readable descriptor dump
```

### Data classes

* `DeviceInfo(vendor_id, product_id, manufacturer, product, serial, known_product)`
* `ConfigurationInfo(value, max_power_ma, interfaces)`
* `InterfaceInfo(number, interface_class, subclass, protocol, endpoints)`
* `EndpointInfo(address, attributes, max_packet_size)`

### Exceptions

* `UsbError` — pyusb unavailable or device missing/inaccessible.

---

## `chu2.dsp` — DSP transport & KTMicro protocol

The CHU 2's DSP is configured over HID interface 3 through Windows' own
driver (`hidapi`) — no driver install or admin rights needed. This is the
transport the CLI, GUI and `DeviceService` use.

```python
class HidTransport:                    # context manager
    @classmethod open() -> HidTransport    # raises UsbError if the CHU 2 is absent
    write(data: bytes) -> int              # raises UsbError on an OS/value error or a negative result
    read(length=64, timeout=1000) -> bytes # raises UsbError on an OS/value error; b"" on a plain timeout
    product() -> str
    manufacturer() -> str
    close() -> None

hid_present() -> bool                  # True when the CHU 2's control channel is plugged in
```

### KTMicro EQ protocol (`docs/PROTOCOL.md` §2c)

Every function below takes a ``transport`` with the `HidTransport` contract —
`write(report: bytes) -> int` and `read(length, timeout_ms) -> bytes`
(returning `b""` on timeout). `HidTransport` and `chu2.fake_device.FakeChu2`
both satisfy it, so these functions work unchanged against the fake device in
tests.

```python
kt_command(transport, payload: bytes) -> bytes          # one command -> 4 value bytes; raises UsbError on no reply
kt_packet(reg, cmd, value=bytes(4)) -> bytes             # 10-byte payload
kt_read_eq(transport) -> tuple[int, list[FilterBand]]    # (slot, 5 bands) as played now
kt_write_band(transport, index, band) -> tuple[bytes, bytes]  # play now, no commit
kt_verify_band(transport, index, values) -> bool         # read-back == what was written
kt_set_slot(transport, slot) -> None                     # KT_SLOT_ON (0x03) / KT_SLOT_OFF (0x02), no commit
kt_commit(transport) -> None                             # save; the CHU 2 then restarts
kt_write_eq(transport, bands, commit=True) -> None       # fit, write, verify each, then commit
kt_fit_bands(bands) -> list[FilterBand]                  # ≤5 bands, PK/shelves, ±12 dB, 20-20000 Hz, Q 0.1-10, finite
kt_encode_band(band) -> tuple[bytes, bytes]
kt_decode_band(gain_freq, q_type) -> FilterBand          # raises UsbError on an unknown type code
```

`kt_fit_bands` raises `ValueError` (not `UsbError`) for a band the DSP simply
cannot represent: too many bands, an unsupported type, or a non-finite or
out-of-range frequency/gain/Q.

Example:

```python
from chu2 import dsp

with dsp.HidTransport.open() as transport:
    slot, bands = dsp.kt_read_eq(transport)
```

### Research tools — `chu2.research` (pyusb, need the `research` extra)

`chu2.research` holds `DspTransport`, `hid_probe()`, `probe()` and
`test_commands()`: the old pyusb-based
research tools from before the KTMicro protocol was found (see
`RESEARCH_REPORT.md`). They need `pip install -e ".[research]"` and a Zadig
WinUSB driver bound to interface 3 (`docs/WINDOWS_SETUP.md`); they do not work
against the HID transport above.

```python
class DspTransport:                    # context manager, pyusb-based
    @classmethod open() -> DspTransport
    write_out(data, timeout=1000) -> int
    read_in(length=16, timeout=1000) -> bytes
    control_transfer(command) -> bytes

@dataclass
class ControlCommand:                  # a USB control request
    bm_request_type: int
    b_request: int
    w_value: int
    w_index: int = DSP_INTERFACE
    data_or_wlength: Any = 0
    timeout: int = 1000

hid_probe(transport=None) -> list[ProbeResult]  # HID open + one read, no writes
candidate_commands() -> list[ControlCommand]
probe(transport=None) -> list[ProbeResult]
test_commands(transport=None) -> list[CommandResult]
format_probe_results(results) -> str
format_command_results(results) -> str
```

---

## `chu2.device_service` — owns the CHU 2 on one worker thread

`DeviceService` is the state machine the app drives (spec §4.2). The app
never touches USB directly: it calls the public methods below (safe from any
thread) and receives events through `on_event(name, data)`, which runs **on
the worker thread** and must return quickly and never block.

```python
class DeviceService:
    def __init__(
        open_transport: Callable[[], Any],     # e.g. dsp.HidTransport.open, or FakePlug().open
        is_present: Callable[[], bool],        # e.g. dsp.hid_present, or FakePlug().is_present
        on_event: Callable[[str, dict], None],
        poll_s: float = 1.0,
        restart_timeout_s: float = 60.0,       # how long a save waits for the CHU 2 to come back
        still_waiting_s: float = 8.0,          # when the "still_waiting" step is sent
        reopen_tries: int = 3,                 # opens tried after the restart
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    )

    connected: bool                        # property; safe from any thread
    start() -> None                        # start the worker thread; a no-op if one is already running
    stop() -> None                         # send pending live edits and EQ switches, stop, close (a queued save is dropped)
    set_band_live(index, band) -> None     # play now; raises ValueError for a band the DSP can't store
    set_eq_enabled(on: bool) -> None       # queue a slot on/off, no commit
    save(bands) -> None                    # queue write -> verify -> commit -> wait for restart -> verify again
    run_once(now=None) -> None             # drive one iteration directly (what tests use instead of start())
```

Events sent to `on_event`:

```
connected       {"slot": int, "bands": [FilterBand x 5]}
disconnected    {"reason": str}
error           {"code": "open_failed" | "unknown_filter_type" | "internal", "message": str}
eq_enabled      {"on": bool}
save_progress   {"step": "writing" | "committing" | "restarting" | "still_waiting" | "verifying"}
saved           {"bands": [FilterBand x 5], "slot": int}
save_failed     {"reason": str, "after_commit": bool, ...}
```

`save_failed` reasons. Nothing was saved: `invalid_bands` (+ `message`),
`write_failed` (+ `message`; the connection is dropped), `write_mismatch`
(+ `mismatched`: band indexes; never committed). After the commit the outcome
is unknown until the CHU 2 is read again: `commit_unknown` (+ `message`),
`no_restart` (it never dropped off USB), `restart_timeout` (it did not come
back within `restart_timeout_s`), `verify_unavailable` (+ `message`),
`verify_mismatch` (+ `bands`: what it stored). An `unknown_filter_type` error
is sent once; the service then waits for the CHU 2 to be unplugged.

---

## `chu2.app.api` — the object the window's page talks to

`Api(store, push, close_window, dialogs=None)` is exposed to the page as
`window.pywebview.api`. Most public methods return the state snapshot
(JSON-friendly); device changes are pushed as `push("state", snapshot)`.
Snapshots carry a growing `rev`, so the page ignores an older one, plus the
EQ's `name`, the last Quick Tune choice (`quick`), `settings` and `version`.

```python
get_state() / set_band(index, band) / set_eq_enabled(on) / set_auto_preamp(on)
reset_bands() / set_design(bands, name=None)  # all 5 bands flat (0 dB); Undo; Import to editor
apply_preset(id) / quick_tune(scene, tweaks, intensity)   # play now, not saved
free_smallest_band() / save() / cancel_save() / dismiss_save()
restore_original() / close_app("discard" | "save")
set_setting("theme" | "confirm_save", value) / open_data_folder()

# these answer with something else than the snapshot
get_library() -> {"presets": [...], "recipes": quicktune.recipes()}
save_preset(name, tags) / rename_preset(id, name) / delete_preset(id)
set_favourite(id, on)                                     # -> the library
import_file() / import_text(text, name="")  # -> transfer preview | {"error"} | {"cancelled"}
export_file("apo" | "json")                 # -> {"saved": path} | {"error"} | {"cancelled"}
share_code()                                # -> {"code", "text"}
```

`dialogs` is `chu2.app.main.Dialogs` (the window's native Open / Save
dialogs); without it, import and export answer `{"error": …}`.

Opening the app never changes the sound: the CHU 2 keeps playing its stored
EQ until the first edit; after that it plays what Save would store (design →
`chu2.preamp` → device bands). Methods starting with `_` are for
`chu2.app.main` and tests.

---

## `chu2.eq` — EQ model & biquad math

```python
@dataclass
class FilterBand:                      # one parametric band
    type: str = "peaking"              # see FILTER_TYPES
    frequency: float = 1000.0          # Hz
    gain: float = 0.0                  # dB
    q: float = 1.0

@dataclass
class Biquad:                          # normalized coefficients (a0 = 1)
    b0, b1, b2, a1, a2: float
    apply(samples) -> list[float]
    response(frequency, sample_rate) -> complex

@dataclass
class Equalizer:
    bands: list[FilterBand]
    sample_rate: int = DEFAULT_SAMPLE_RATE
    coefficients() -> list[Biquad]
    magnitude_response_db(frequencies) -> list[float]

FILTER_TYPES = ("peaking", "low_shelf", "high_shelf", "lowpass",
                "highpass", "bandpass", "notch", "allpass")

band_coefficients(band, sample_rate) -> Biquad
log_frequency_axis(f_min=20, f_max=20000, points=256) -> list[float]
```

All coefficient functions implement the RBJ audio-EQ-cookbook equations:
`peaking_coefficients`, `low_shelf_coefficients`, `high_shelf_coefficients`,
`lowpass_coefficients`, `highpass_coefficients`, `bandpass_coefficients`,
`notch_coefficients`, `allpass_coefficients`.

---

## `chu2.preamp` — the preamp built from the bands (spec §4.4)

The CHU 2 has no usable preamp register, so boosts are made safe inside the
bands: shelf boosts are stored as the opposite shelf cut (same shape, quieter),
then a free band becomes a nearly flat trim (high shelf at 20 Hz) if the
curve still goes above 0 dB.

```python
compute(bands, auto=True) -> PreampResult   # never changes its input
PreampResult.bands          # 5 FilterBands to play and store
PreampResult.preamp_db      # total level change, <= 0
PreampResult.peak_db / peak_hz / device_peak_db
PreampResult.method         # "none" | "flip" | "trim" | "flip+trim"
PreampResult.flipped / trim_index / warning   # warning: None | "no_free_band" | "trim_limit"
PreampResult.to_dict()      # the numbers for the UI, rounded
peak(bands) -> (dB, Hz)
flip_shelf(band) -> FilterBand
```

---

## `chu2.store` — the app's files

`%APPDATA%\CHU2Studio\` (or `$CHU2STUDIO_HOME`): `backup.json` (the EQ the
CHU 2 had when this PC first saw it; written once, never overwritten),
`settings.json` (`{"auto_preamp": true, "theme": "atelier", "confirm_save": true}`),
`last_saved.json` (the design and name behind the last save), `presets\`
(the user's `.chu2.json` presets), `favourites.json`, and, for the `.exe`,
`chu2-studio.log`. A `--fake-device` run uses the `fake-device\` subfolder.

```python
THEMES = ("atelier", "mocha", "sage", "latte", "porcelain")
Store(root=None)
read_backup() -> dict | None               # {"saved_at", "slot", "bands"}
write_backup_once(slot, bands) -> bool     # False if a backup already exists
load_settings() -> dict / save_settings(dict)
read_last_saved() -> dict | None / write_last_saved(design, device, name="")
load_favourites() -> list[str] / save_favourites(ids)
```

---

## `chu2.quicktune` — Quick Tune recipes (brief §4, spec §5)

Five scenes (`music`, `gaming`, `movies`, `fps`, `calls`; exclusive) and
six tweaks (`sub_bass`, `clean_bass`, `softer_vocals`, `clearer_voices`,
`less_sharp`, `sparkle`; each owns its slot(s), two that own the same slot
conflict). Intensity `subtle` / `standard` / `strong` scales gains ×0.5 / ×1 /
×1.5, rounded half away from zero, boosts capped at +6 dB and cuts at −8 dB.

```python
IDLE_DESIGN                                  # the 5 idle slots at 0 dB (also the reset)
compose(scene, tweaks, intensity) -> (design, notes)   # notes: "Replaces band 4 of FPS."
explain(scene, tweaks) -> list[str]          # plain-English "what changed"
conflicts(tweak) -> list[str]              # compose() refuses two that conflict
recipes() -> {"scenes", "tweaks", "intensities"}      # for the page
```

---

## `chu2.sharecode` — share codes (brief S7)

`CHU2-1.<name>.<payload>.<CRC-16>`: base64url of the five bands packed 41 bits
each (type, frequency in Hz, gain in 0.1 dB, Q ×1000, exactly what the CHU 2
stores) and a CRC-16/CCITT-FALSE, so a typo is caught. No server.

```python
encode(name, bands: list[FilterBand]) -> str
decode(code) -> (name, list[FilterBand])     # ShareCodeError (a ValueError) if wrong
find_code(text) -> str | None                # the first code anywhere in a text
describe(bands) -> str                       # "LS 80 Hz +3.5 Q0.71 · PK 250 Hz −2.0 Q1.00"
safe_name(name) -> str                       # url-safe, also used for file names
```

---

## `chu2.transfer` — import and export (brief S7)

```python
read_text(text, source_name="") -> preview   # TransferError (a ValueError) if nothing usable
export_apo(name, design, preamp_db) -> str   # Equalizer APO / AutoEq text
export_json(name, design, tags=()) -> str    # a .chu2.json preset
preset_document(name, design, tags=()) -> dict
```

`read_text` understands a share code anywhere in the text, a `.chu2.json`
preset, and Equalizer APO / AutoEq / Peace lines. The preview is
`{"name", "format", "filters": [{"n", "code", "type", "frequency", "gain", "q",
"bypass", "status"}], "total", "bands" (5), "preamp", "peak_db", "notes"}`:
other filter types are listed as "isn't available on CHU 2", values are
clamped, and with more than five filters the five largest are kept. The file's
preamp is shown, not copied.

---

## `chu2.library` — the preset library (brief S6)

```python
Library(store)
presets() -> list[dict]     # {"id", "name", "group", "tags", "bands", "about", "favourite", ...}
find(id) -> dict            # LibraryError (a ValueError) if unknown
save(name, tags, design) -> dict / rename(id, name) / delete(id) / set_favourite(id, on)
```

Ids: `official:flat`, `official:backup` (the first-seen backup), `scene:<id>`
(Quick Tune at standard intensity), `mine:<slug>` (a file in `presets\`).
Path-like ids are rejected. `Api.get_library` adds `on_chu2` (the preset is
what the CHU 2 stores).

---

## `chu2.preset` — preset management

```python
@dataclass
class Preset:
    name: str
    bands: list[FilterBand]
    description: str = ""
    sample_rate: int = DEFAULT_SAMPLE_RATE
    version: int = SCHEMA_VERSION
    to_dict() -> dict
    to_json(indent=2) -> str
    equalizer() -> eq.Equalizer

validate(data: dict) -> list[str]       # returns problems ([] == valid)
preset_from_dict(data) -> Preset
load(path) -> Preset
save(preset, path) -> None
discover(directory) -> list[str]        # JSON presets under a directory
to_equalizer_apo(preset) -> str         # EqualizerAPO config
to_coefficients_csv(preset) -> str
flat_preset(name="Default (Flat)") -> Preset
```

### Preset JSON format

```json
{
  "version": 1,
  "name": "My preset",
  "description": "Optional notes",
  "sample_rate": 48000,
  "bands": [
    {"type": "peaking", "frequency": 1000.0, "gain": 3.0, "q": 1.0}
  ]
}
```

Ranges enforced by `validate`: frequency 20–20000 Hz, gain −12…+12 dB, Q 0.1–20.

---

## `chu2.cli` & `chu2.gui`

```python
from chu2.cli import main    # main(argv=None) -> int
from chu2.gui import main    # main(argv=None) -> int
```

See `README.md` for the CLI command reference.
