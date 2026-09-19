# DSP Protocol (Reverse-Engineering Notes)

This document records everything we know about how the Moondrop CHU 2's DSP is
configured, and separates **confirmed facts** from **working hypotheses**. It is
the living reference that the code in `src/chu2/dsp.py` is built on.

> ✅ **Status: command format found** (see *Command format — FOUND* in §2c).
> Reads, writes and commit confirmed on our unit. Use `chu2 dsp read / write /
> restore` (`src/chu2/dsp.py`, `kt_*` functions).
> Sections 3–4 are the original hypotheses and are now obsolete.

---

## 1. USB topology (confirmed)

The CHU 2 is a composite USB device with vendor/product IDs:

| Field       | Value    |
|-------------|----------|
| Vendor ID   | `0x31B2` (Moondrop) |
| Product ID  | `0x0113` (CHU 2 DSP) |

It exposes at least two logical interfaces:

| Interface | Class | Purpose                     |
|-----------|-------|-----------------------------|
| 0 (etc.)  | `0x01` Audio | UAC1 playback — handled by the OS audio stack |
| **3**     | `0x03` HID-like | **DSP control** — our target |

Interface 3 endpoints:

| Endpoint | Direction | Purpose        |
|----------|-----------|----------------|
| `0x03`   | OUT       | Host → DSP     |
| `0x83`   | IN        | DSP → Host     |

**Confirmation command** (Phase 1 of the plan):

```powershell
Get-PnpDevice | Where-Object { $_.InstanceId -match "VID_31B2&PID_0113" } |
    Select-Object FriendlyName, Class, Driver
```

Expected result:

```
FriendlyName       Class                     Driver
------------       -----                     ------
Chu2 DSP           Media                    audioendpoint.inf
```

---

## 1b. Windows access problem (confirmed)

On Windows, Interface 3 (`MI_03`) enumerates as a HID **"Consumer Control"**
device — `HID\VID_31B2&PID_0113&MI_03`, usage page `0x000C`, driven by
`hidserv.inf`. This has a direct consequence:

* Windows' input stack classifies Consumer Control devices as **system devices**
  (media keys) and does **not** publish a user-mode HID device interface for
  them. So `hidapi` returns an empty list, `CreateFile` on the interface path
  returns `ERROR_FILE_NOT_FOUND`, and any app using the normal HID API (this is
  why the official Moondrop Hub cannot find the CHU 2) never sees it.

**Consequence for this tool:** on Windows, standard HID access is not available.
The DSP must be reached by *replacing* the HID driver on Interface 3 with
**WinUSB** (via Zadig), then talking to it over raw USB (libusb/pyusb). Audio
(Interface 0) must never be touched.

See `docs/WINDOWS_SETUP.md` for the exact steps.

---

## 2. What we know about the DSP chip

The CHU 2 uses a **KTMicro KT0210-class** USB audio codec/DSP. The KT0210 is a
single-chip USB audio solution (driverless UAC1.0). Its tuning interface is a
vendor/HID channel, which is exactly what Interface 3 is.

Confirmed from the live device (after rebinding Interface 3 to libusb-win32):

* Manufacturer string: `KTMicro`
* Product string: `2020-02-20-0000-0000-0000`
* Serial string: `Chu2 DSP`
* `bcdUSB: 0200`, 1 configuration, Interface 3 = HID (class `0x03`).

Useful references:

* [KTMicro KT0210 product page](https://www.ktmicro.com/?usb_104/301.html)
* [KT0210 / KT0211 / KT0211L comparison](https://warmseaic.com/kt-article/quantum-micro-kt0210-kt0211-kt0211l-comparison)

---

## 2c. HID report descriptor (confirmed — dumped live)

Interface 3's HID report descriptor (70 bytes) decodes to three report IDs:

| Report ID | Direction | Size | Meaning |
|-----------|-----------|------|---------|
| `0x01` | Input | 1 byte | Consumer Control (media keys) — what Windows claims |
| `0x4B` | Input + Output | 10 bytes each | Vendor (usage page `0xFF01`) — DSP channel |
| `0x54` | Input + Output | 10 bytes each | Vendor (usage page `0xFF01`) — DSP channel |

So a DSP command is **`[report_id][10-byte payload]`** written to endpoint
`0x03`, with a 10-byte response read from endpoint `0x83`.

Raw descriptor:

```
05 0c 09 01 a1 01 85 01 15 00 25 01 75 01 95 02 09 e9 09 ea 81 02
95 02 09 cd 09 cf 81 02 95 04 81 01 06 01 ff 85 4b 75 08 95 0a 09 01
81 03 95 0a 09 02 91 02 85 54 75 08 95 0a 09 03 81 03 95 0a 09 04 91 02 c0
```

### Command format — still under reverse-engineering

Confirmed behaviour so far:

* Writing to `0x03` (OUT) succeeds; reading `0x83` (IN) **times out** unless a
  valid command was just written, so the device is write-triggered.
* Vendor control transfers (the Dawn Pro's `0xC0 0xA5` scheme) are **rejected**
  with `ERROR_GEN_FAILURE` — this chip is HID-report-only.
* HID `GET_REPORT` and `SET_REPORT` over the **control pipe** STALL for every
  report ID/type (2026-09-18, `scripts/control_reports.py`), while `GET_IDLE` /
  `SET_IDLE` succeed. Reports travel only over interrupt endpoints `0x03`/`0x83`.
  (`ERROR_GEN_FAILURE` / "device not functioning" is how libusb-win32 reports a
  STALL.)
* The `0xC0 0xA5 <opcode>` grammar does **not** elicit a response through the
  HID reports either.
* The protocol does **not** match the Audiocular-Aura project's `SAVITECH`
  (63-byte), `MOONDROP` (63-byte, report `0x4B`), or `FIIO_JA11` (16-byte,
  report 2) formats. The CHU 2's 10-byte `0x4B`/`0x54` encoding is distinct.
* Brute-force attempts produced **zero** IN responses:
  * first-byte sweep (0x00–0xFF, both report IDs) — nothing,
  * `0xAA 0x0A` / `0xBB 0x0B` headers × opcodes — nothing,
  * 11 magic-pair headers × 256 opcodes × both report IDs (5,632 probes) — nothing.

So the payload is not a simple `[magic2][opcode][zeros]` layout; it has a more
complex structure (likely a length field, checksum, and/or non-zero fixed
fields). Interesting note: report IDs `0x4B`/`0x54` are ASCII **"K"/"T"**
(KTMicro).

### Command format — FOUND (2026-09-18)

Source: [jeromeof/devicePEQ](https://github.com/jeromeof/devicePEQ)
(`devicePEQ/ktmicroUsbHidHandler.js`, and a real CHU 2 capture in
`tests/captures/ktmicro_chu2_dsp.json`). It lists this exact device as
`"Chu2 DSP"` (5 bands, ±12 dB, shelves allowed, no pregain). **Reads and writes
confirmed on our unit.** A write shows on read-back at once, before any commit
(`scripts/write_test.py`, band 0 −1.5 → −1.0 → −1.5 dB). The commit is acked,
then **the CHU 2 drops off USB and restarts** (audio stops briefly); a command
1 s later finds no device; it is back ~1–1.5 s after the commit. A committed EQ
(including shelf types 3/4) survives this restart. A write without commit
does **not** survive unplugging: an unsaved edit is lost and the last
committed EQ comes back (test #23).

All commands use report `0x4B` on interrupt OUT `0x03`. The reply comes back on
`0x83` with report `0x4B` and echoes bytes 0 and 4. Report `0x54` is unused. No
checksum.

```
byte:  0    1  2  3  4    5  6    7    8    9
      reg   00 00 00 cmd  00 v0   v1   v2   v3
cmd:  0x52 'R' read · 0x57 'W' write · 0x53 'S' commit (reg 0x00) · 0x43 'C' clear (unused)
```

| Register | Meaning | Value bytes |
|----------|---------|-------------|
| `0x24` | EQ slot: `0x03` = custom/on, `0x02` = off | v0 = slot (send v0 = `0x03` on read too) |
| `0x26 + 2*i` | band *i* (0–4) gain + frequency | v0-v1 = gain × 10, signed LE16 · v2-v3 = Hz, LE16 |
| `0x27 + 2*i` | band *i* Q + type | v0-v1 = Q × 1000, LE16 · v2 = type (0 PK, 3 low shelf, 4 high shelf) |
| `0x66` | pregain | v0 = dB, signed byte (writes ack and read back, but have no audible effect live — tests #19–#20) |

Write sequence used by devicePEQ: read `0x24`; if it is `0x02`, write `0x24` =
`0x03`; write the 10 band registers; send commit `[00 00 00 00 53 00 00 00 00 00]`;
wait ~1 s. The CHU 2 answers every write with `v0 = 0x03`.

Why the brute force missed it: every probe had `0x00` in byte 4, the command byte.

### APK analysis (done — the official apps do NOT support the CHU 2)

Both official Android apps were downloaded and decompiled to look for the
protocol:

* `MOONDROP LINK` (`com.moondroplab.moondroplink`, React Native)
* `MOONDROP` (`com.moondroplab.moondrop.moondrop_app`, Flutter)

Result: neither contains any CHU 2 / KT0210 / `0x31B2` device-matching code or
`0x4B`/`0x54` report handling. The `MOONDROP` app only implements:

* **Conexant** (`com.conexant.*`, `CX2070x`, `FreemanCnxtUsbDevice`) — FreeDSP
  cable, vendor control transfers.
* **Airoha** (`com.airoha.*`) — TWS earbud PEQ over Bluetooth.
* **Comtrue** (`ct*` classes) — Dawn Pro, 63-byte report `0x4B`.

This **confirms the project premise**: the CHU 2 DSP is genuinely unsupported by
Moondrop's software, so there is no official protocol to extract. The 10-byte
KTMicro format must be reverse-engineered directly — either by brute-forcing the
command space (we have write access), or by obtaining the KT0210 SDK/datasheet
from KTMicro, which documents the HID command format for OEMs.




---

## 3. Communication approach (hypothesis)

Two mechanisms are plausible for Interface 3:

### 3a. HID reports over control transfers
* `SET_REPORT` (`bmRequestType=0x21`, `bRequest=0x09`) with `wValue=0x0200`
  (report type 2 = output, report ID 0) — this is the candidate the plan tests
  first.
* `GET_REPORT` (`bmRequestType=0xA1`, `bRequest=0x01`) to read state back.

### 3b. Interrupt endpoint I/O
* Write the command payload to endpoint `0x03` and read the response from
  `0x83`. This is the "safe probe" path from Phase 2.

We do not yet know which one the device actually uses — that is what the probe
and capture steps are for.

---

## 4. Candidate command table

The brute-force script (`scripts/test_commands.py`) tries these first:

| # | bmRequestType | bRequest | wValue | wIndex | Direction |
|---|---------------|----------|--------|--------|-----------|
| 1 | `0x21` (class, iface, out) | `0x09` SET_REPORT | `0x0200` | 3 | SET |
| 2 | `0x21` | `0x01` GET_REPORT (mis-typed probe) | `0x0000` | 3 | SET |
| 3 | `0xA1` (class, iface, in) | `0x01` GET_REPORT | `0x0000` | 3 | GET (16 bytes) |
| 4 | `0x40` (vendor, out) | `0x00` | `0x0000` | 3 | SET |

---

## 5. Interpreting probe results

| Observed behaviour | Likely meaning | Next step |
|--------------------|----------------|-----------|
| OUT/IN transfers succeed | DSP channel is accessible | Capture traffic; map commands |
| "Access denied" / "Operation not permitted" | OS driver holds the interface | Run as admin; or use Zadig to bind **WinUSB to Interface 3 only** |
| "Not functioning" / stall | Interface not in a ready state | DSP may need a wake-up command |
| Sound still works after probing | Audio interface untouched | Continue safely |

---

## 6. Recording new findings

When you discover a working command, record it here under a dated entry:

```markdown
### 2024-XX-XX — <author>
* Command: bmRequestType=0x21 bRequest=0x09 wValue=0x???? wIndex=3, payload=...
* Observed: <response / behaviour>
* Confidence: confirmed | hypothesis
* Notes: ...
```

Then add it to `src/chu2/dsp.py` (the command table) so the CLI and GUI share it.

---

## 7. Open questions

1. Is the EQ a **10-band parametric EQ** (as on other KT0210 products) or a
   different band count?
2. What is the payload layout — gain as 0.25 dB steps? frequency as Hz or an
   index? Q as a fixed-point value?
3. Does the device report its current state via `GET_REPORT`, or is it
   write-only?
4. Are presets stored in DSP flash, and can they be enumerated over USB?
