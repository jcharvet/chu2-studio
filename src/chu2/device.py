"""USB discovery and descriptor inspection for the Moondrop CHU 2 (DSP variant).

``pyusb`` and ``hidapi`` are imported lazily so that the parts of the package
that do not need a physical device (EQ math, preset management, the offline CLI
commands) keep working even when the native USB stacks are not installed.

The CHU 2 presents itself as a composite USB device:

* A standard UAC1 audio interface for playback (handled by the OS audio stack).
* A separate HID-like "Interface 3" used for DSP configuration, exposing
  endpoints ``0x03`` (OUT) and ``0x83`` (IN).

Only Interface 3 is touched by this tool; the audio interface is left alone.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Iterator, List, Optional, Tuple

# Moondrop vendor ID and the CHU 2 (DSP) product ID.
MOONDROP_VID: int = 0x31B2
CHU2_DSP_PID: int = 0x0113

# DSP control interface and endpoints.
DSP_INTERFACE: int = 3
DSP_EP_OUT: int = 0x03
DSP_EP_IN: int = 0x83

#: Known Moondrop DSP products. The tool targets the CHU 2 first but can
#: discover other KTMicro-DSP devices that share the same vendor ID.
KNOWN_DSP_PRODUCTS: Dict[Tuple[int, int], str] = {
    (MOONDROP_VID, CHU2_DSP_PID): "Moondrop CHU 2 (DSP)",
}

# USB interface classes we care about when dumping descriptors.
_CLASS_NAMES: Dict[int, str] = {
    0x01: "Audio",
    0x03: "HID",
    0xFF: "Vendor-specific",
}


class UsbError(RuntimeError):
    """Raised when pyusb is unavailable or a device operation fails."""


@dataclasses.dataclass
class DeviceInfo:
    """A lightweight summary of a USB device, decoupled from pyusb objects."""

    vendor_id: int
    product_id: int
    manufacturer: Optional[str]
    product: Optional[str]
    serial: Optional[str]
    known_product: Optional[str] = None

    @property
    def vid_pid(self) -> str:
        return f"{self.vendor_id:04X}:{self.product_id:04X}"

    def __str__(self) -> str:
        label = self.product or self.known_product or "Unknown device"
        return f"{self.vid_pid}  {label}"


@dataclasses.dataclass
class EndpointInfo:
    """Descriptor summary for a single endpoint."""

    address: int
    attributes: int
    max_packet_size: int


@dataclasses.dataclass
class InterfaceInfo:
    """Descriptor summary for a single interface."""

    number: int
    interface_class: int
    subclass: int
    protocol: int
    endpoints: List[EndpointInfo]


@dataclasses.dataclass
class ConfigurationInfo:
    """Descriptor summary for a single configuration."""

    value: int
    max_power_ma: int
    interfaces: List[InterfaceInfo]


def _pyusb():
    """Lazily import and return the ``usb`` package, raising a friendly error."""
    try:
        import usb.core  # type: ignore
        import usb.util  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise UsbError(
            "pyusb is not installed. Install it with: pip install -e \".[research]\"\n"
            "On Windows you also need a Zadig WinUSB driver bound to the DSP "
            "interface (see docs/WINDOWS_SETUP.md)."
        ) from exc
    return usb


def _hidapi():
    """Lazily import ``hid`` (hidapi), raising a friendly error."""
    try:
        import hid  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise UsbError(
            "hidapi is not installed. Install it with: pip install hidapi"
        ) from exc
    return hid


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def find_chu2() -> Optional[Any]:
    """Return the pyusb device for the CHU 2 DSP, or ``None`` if not found."""
    usb = _pyusb()
    return usb.core.find(idVendor=MOONDROP_VID, idProduct=CHU2_DSP_PID)


def require_chu2() -> Any:
    """Return the CHU 2 device or raise :class:`UsbError` with guidance."""
    dev = find_chu2()
    if dev is None:
        raise UsbError(
            "Moondrop CHU 2 (DSP) not found. Is it plugged in?\n"
            f"Looking for VID:PID = {MOONDROP_VID:04X}:{CHU2_DSP_PID:04X}."
        )
    return dev


def enumerate_devices() -> List[DeviceInfo]:
    """Enumerate every USB device currently visible to pyusb."""
    usb = _pyusb()
    out: List[DeviceInfo] = []
    for dev in usb.core.find(find_all=True):
        try:
            manufacturer = dev.manufacturer
        except Exception:
            manufacturer = None
        try:
            product = dev.product
        except Exception:
            product = None
        try:
            serial = dev.serial_number
        except Exception:
            serial = None

        out.append(
            DeviceInfo(
                vendor_id=dev.idVendor,
                product_id=dev.idProduct,
                manufacturer=manufacturer,
                product=product,
                serial=serial,
                known_product=KNOWN_DSP_PRODUCTS.get(
                    (dev.idVendor, dev.idProduct)
                ),
            )
        )
    return out


def list_hid_devices() -> List[Dict[str, Any]]:
    """Enumerate HID devices via hidapi.

    Returns a list of dicts mirroring ``hid.enumerate()``.
    """
    hid = _hidapi()
    return [dict(device) for device in hid.enumerate()]


def find_chu2_hid_paths() -> List[Dict[str, Any]]:
    """Return hidapi entries for the CHU 2 DSP (interface 3).

    The DSP control interface enumerates as a HID *Consumer Control* device on
    Windows, which Windows shares with apps: no elevation is needed and the
    input stack does not claim it exclusively (test #17). This helper is the
    targeted lookup used by the HID transport.
    """
    hid = _hidapi()
    return [
        dict(device)
        for device in hid.enumerate(MOONDROP_VID, CHU2_DSP_PID)
    ]


# --------------------------------------------------------------------------- #
# Descriptor inspection
# --------------------------------------------------------------------------- #
def _endpoint_info(ep: Any) -> EndpointInfo:
    return EndpointInfo(
        address=ep.bEndpointAddress,
        attributes=ep.bmAttributes,
        max_packet_size=ep.wMaxPacketSize,
    )


def inspect_device(dev: Any) -> List[ConfigurationInfo]:
    """Return a structured dump of a pyusb device's descriptors."""
    configs: List[ConfigurationInfo] = []
    for cfg in dev:
        interfaces: List[InterfaceInfo] = []
        for intf in cfg:
            endpoints = [_endpoint_info(ep) for ep in intf]
            interfaces.append(
                InterfaceInfo(
                    number=intf.bInterfaceNumber,
                    interface_class=intf.bInterfaceClass,
                    subclass=intf.bInterfaceSubClass,
                    protocol=intf.bInterfaceProtocol,
                    endpoints=endpoints,
                )
            )
        max_power = getattr(cfg, "bMaxPower", 0) * 2
        configs.append(
            ConfigurationInfo(
                value=cfg.bConfigurationValue,
                max_power_ma=max_power,
                interfaces=interfaces,
            )
        )
    return configs


def find_interface_endpoints(dev: Any, interface_number: int) -> List[EndpointInfo]:
    """Return endpoint descriptors for ``interface_number`` across all configs."""
    for cfg in dev:
        for intf in cfg:
            if intf.bInterfaceNumber == interface_number:
                return [_endpoint_info(ep) for ep in intf]
    return []


def class_name(interface_class: int) -> str:
    return _CLASS_NAMES.get(interface_class, f"0x{interface_class:02X}")


def format_device_report(dev: Any) -> str:
    """Render a human-readable descriptor report for the CLI/GUI."""
    lines: List[str] = []
    try:
        lines.append(f"Manufacturer : {dev.manufacturer}")
    except Exception:
        lines.append("Manufacturer : (unavailable)")
    try:
        lines.append(f"Product      : {dev.product}")
    except Exception:
        lines.append("Product      : (unavailable)")
    try:
        lines.append(f"Serial       : {dev.serial_number}")
    except Exception:
        lines.append("Serial       : (unavailable)")

    for cfg in inspect_device(dev):
        lines.append(f"Configuration {cfg.value} (max power {cfg.max_power_ma} mA)")
        for intf in cfg.interfaces:
            lines.append(
                f"  Interface {intf.number}: class={class_name(intf.interface_class)} "
                f"({intf.interface_class:02X}) subclass={intf.subclass:02X} "
                f"protocol={intf.protocol:02X}"
            )
            for ep in intf.endpoints:
                direction = "IN " if ep.address & 0x80 else "OUT"
                lines.append(
                    f"    Endpoint {ep.address:02X} ({direction}): "
                    f"type={ep.attributes:02X} max_packet={ep.max_packet_size}"
                )
    return "\n".join(lines)
