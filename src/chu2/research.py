"""Research tools from before the KTMicro protocol was found (RESEARCH_REPORT.md).

``DspTransport`` talks to the CHU 2 through **pyusb/libusb**, which needs a
Zadig WinUSB driver on interface 3 (docs/WINDOWS_SETUP.md); install the
``research`` extra. The app and ``chu2 dsp`` do not use this module: they use
:class:`chu2.dsp.HidTransport` through Windows' own HID driver.
"""

from __future__ import annotations

import dataclasses
from typing import Any, List, Optional, Sequence

from . import device as device_mod
from .dsp import HidTransport


# --------------------------------------------------------------------------- #
# pyusb transport
# --------------------------------------------------------------------------- #
class DspTransport:
    """Wrap a pyusb device and expose the DSP interface.

    Use as a context manager to guarantee resources are released::

        with DspTransport.open() as dsp:
            dsp.write_out(b"...")
    """

    def __init__(self, dev: Any):
        self.dev = dev
        self._out_ep = None
        self._in_ep = None

    @classmethod
    def open(cls) -> "DspTransport":
        """Open the CHU 2 DSP interface, raising :class:`UsbError` if absent."""
        dev = device_mod.require_chu2()
        dsp = cls(dev)
        dsp._claim()
        return dsp

    def _claim(self) -> None:
        # ponytail: no set_configuration() — the DSP works without it
        # (scripts/write_test.py), and on this composite device it is a
        # device-wide request that could re-initialize the audio interface.
        self._out_ep = None
        self._in_ep = None
        for cfg in self.dev:
            for intf in cfg:
                if intf.bInterfaceNumber != device_mod.DSP_INTERFACE:
                    continue
                for ep in intf:
                    if ep.bEndpointAddress == device_mod.DSP_EP_OUT:
                        self._out_ep = ep
                    elif ep.bEndpointAddress == device_mod.DSP_EP_IN:
                        self._in_ep = ep

    def close(self) -> None:
        try:
            device_mod._pyusb().util.dispose_resources(self.dev)
        except Exception:
            pass

    def __enter__(self) -> "DspTransport":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- raw I/O ------------------------------------------------------------ #
    def write_out(self, data: bytes, timeout: int = 1000) -> int:
        if self._out_ep is None:
            raise device_mod.UsbError(
                f"OUT endpoint {device_mod.DSP_EP_OUT:02X} not found on "
                f"interface {device_mod.DSP_INTERFACE}."
            )
        return self._out_ep.write(data, timeout=timeout)

    def read_in(self, length: int = 16, timeout: int = 1000) -> bytes:
        if self._in_ep is None:
            raise device_mod.UsbError(
                f"IN endpoint {device_mod.DSP_EP_IN:02X} not found on "
                f"interface {device_mod.DSP_INTERFACE}."
            )
        return self._in_ep.read(length, timeout=timeout).tobytes()

    def control_transfer(self, command: "ControlCommand") -> bytes:
        return self.dev.ctrl_transfer(
            bmRequestType=command.bm_request_type,
            bRequest=command.b_request,
            wValue=command.w_value,
            wIndex=command.w_index,
            data_or_wLength=command.data_or_wlength,
            timeout=command.timeout,
        )


def hid_probe(transport: Optional[HidTransport] = None) -> List[ProbeResult]:
    """Probe the DSP over HID and report what is reachable.

    This never writes DSP state — it only opens the device, reads its identity,
    and optionally attempts one read to confirm the report channel is alive.
    """
    owns = transport is None
    if transport is None:
        transport = HidTransport.open()

    results: List[ProbeResult] = []
    try:
        results.append(
            ProbeResult(
                step="open",
                ok=True,
                detail=(
                    f"{transport.manufacturer()} {transport.product()} "
                    f"(VID:{device_mod.MOONDROP_VID:04X} PID:{device_mod.CHU2_DSP_PID:04X})"
                ),
            )
        )
    except Exception as exc:
        results.append(ProbeResult(step="open", ok=False, detail=str(exc)))

    try:
        data = transport.read(64, timeout=1000)
        results.append(
            ProbeResult(step="read", ok=True, detail="read succeeded.", data=data)
        )
    except Exception as exc:
        # A stall/timeout on read is expected for a write-mostly device.
        results.append(ProbeResult(step="read", ok=False, detail=str(exc)))

    if owns:
        transport.close()
    return results


@dataclasses.dataclass
class ControlCommand:
    """A USB control-transfer request targeting the DSP interface."""

    bm_request_type: int
    b_request: int
    w_value: int
    w_index: int = device_mod.DSP_INTERFACE
    data_or_wlength: Any = 0
    timeout: int = 1000

    def describe(self) -> str:
        direction = "SET" if (self.bm_request_type & 0x80) == 0 else "GET"
        return (
            f"{direction} req=0x{self.b_request:02X} value=0x{self.w_value:04X} "
            f"index=0x{self.w_index:02X}"
        )


# --------------------------------------------------------------------------- #
# Candidate command table (Phase 3 of the plan)
# --------------------------------------------------------------------------- #
def candidate_commands() -> List[ControlCommand]:
    """Return the set of candidate HID/vendor commands used for brute-forcing."""
    return [
        # HID-like SET commands
        ControlCommand(bm_request_type=0x21, b_request=0x09, w_value=0x0200,
                       data_or_wlength=b"\x01\x00\x00\x00"),
        ControlCommand(bm_request_type=0x21, b_request=0x01, w_value=0x0000,
                       data_or_wlength=b"\x01\x00\x00\x00"),
        # HID-like GET commands
        ControlCommand(bm_request_type=0xA1, b_request=0x01, w_value=0x0000,
                       data_or_wlength=16),
        # Vendor-specific commands
        ControlCommand(bm_request_type=0x40, b_request=0x00, w_value=0x0000,
                       data_or_wlength=b"\x01\x00\x00\x00"),
    ]


# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #
@dataclasses.dataclass
class ProbeResult:
    """Outcome of a single probe step."""

    step: str
    ok: bool
    detail: str = ""
    data: Optional[bytes] = None


@dataclasses.dataclass
class CommandResult:
    """Outcome of a single candidate control transfer."""

    command: ControlCommand
    ok: bool
    detail: str = ""
    response: Optional[bytes] = None


# --------------------------------------------------------------------------- #
# Probing
# --------------------------------------------------------------------------- #
def probe(transport: Optional[DspTransport] = None) -> List[ProbeResult]:
    """Run the safe DSP probe and return structured results.

    Only Interface 3 is touched, leaving the audio interface intact.
    """
    if transport is None:
        transport = DspTransport.open()

    results: List[ProbeResult] = []

    results.append(
        ProbeResult(
            step="discover",
            ok=True,
            detail=(
                f"Found VID:{transport.dev.idVendor:04X} "
                f"PID:{transport.dev.idProduct:04X}"
            ),
        )
    )

    # Endpoint check.
    try:
        eps = device_mod.find_interface_endpoints(
            transport.dev, device_mod.DSP_INTERFACE
        )
        if not eps:
            results.append(
                ProbeResult(
                    step="interface",
                    ok=False,
                    detail=f"Interface {device_mod.DSP_INTERFACE} not found.",
                )
            )
        else:
            summary = ", ".join(f"{ep.address:02X}" for ep in eps)
            results.append(
                ProbeResult(
                    step="interface",
                    ok=True,
                    detail=f"Interface {device_mod.DSP_INTERFACE} endpoints: {summary}",
                )
            )
    except Exception as exc:
        results.append(ProbeResult(step="interface", ok=False, detail=str(exc)))

    # OUT transfer.
    try:
        transport.write_out(b"\x00\x00\x00\x00")
        results.append(
            ProbeResult(step="out", ok=True, detail="OUT transfer succeeded.")
        )
    except Exception as exc:
        results.append(ProbeResult(step="out", ok=False, detail=str(exc)))

    # IN transfer.
    try:
        data = transport.read_in(16, timeout=1000)
        results.append(
            ProbeResult(
                step="in",
                ok=True,
                detail="IN transfer succeeded.",
                data=data,
            )
        )
    except Exception as exc:
        results.append(ProbeResult(step="in", ok=False, detail=str(exc)))

    return results


def test_commands(transport: Optional[DspTransport] = None) -> List[CommandResult]:
    """Run the candidate command table and report each result."""
    if transport is None:
        transport = DspTransport.open()

    results: List[CommandResult] = []
    for command in candidate_commands():
        try:
            response = transport.control_transfer(command)
            is_get = (command.bm_request_type & 0x80) != 0
            try:
                response_bytes = bytes(response)
            except Exception:
                response_bytes = None
            results.append(
                CommandResult(
                    command=command,
                    ok=True,
                    detail=(
                        f"response={response_bytes.hex()}"
                        if is_get and response_bytes is not None
                        else "SET accepted"
                    ),
                    response=response_bytes,
                )
            )
        except Exception as exc:
            results.append(
                CommandResult(command=command, ok=False, detail=str(exc))
            )
    return results


def format_probe_results(results: Sequence[ProbeResult]) -> str:
    lines: List[str] = []
    for r in results:
        mark = "OK " if r.ok else "FAIL"
        extra = ""
        if r.data is not None:
            extra = f" data={r.data.hex()}"
        lines.append(f"[{mark}] {r.step}: {r.detail}{extra}")
    return "\n".join(lines)


def format_command_results(results: Sequence[CommandResult]) -> str:
    lines: List[str] = []
    for i, r in enumerate(results, start=1):
        mark = "OK " if r.ok else "FAIL"
        lines.append(f"[{mark}] #{i} {r.command.describe()}: {r.detail}")
    return "\n".join(lines)
