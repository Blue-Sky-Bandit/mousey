"""HID open, send/receive and HID++ 2.0 feature resolution."""

from __future__ import annotations

import time
from dataclasses import dataclass

import hid

from . import hidpp

LOGITECH_VID = 0x046D
# Known G502 HERO product IDs (wired). 0xC08B confirmed on a real device.
G502_HERO_PIDS = {0xC08B}

# On Windows the HID++ reports live on vendor usage page 0xFF00, split into
# two top-level collections: usage 0x01 (short, 7 bytes) and usage 0x02
# (long, 20 bytes). Each must be opened as its own handle.
HIDPP_USAGE_PAGE = 0xFF00
USAGE_SHORT = 0x01
USAGE_LONG = 0x02

DEFAULT_TIMEOUT = 2.0


class DeviceNotFound(Exception):
    pass


class FeatureMissing(Exception):
    pass


@dataclass
class FeatureInfo:
    feature_id: int
    index: int
    type: int
    version: int

    @property
    def name(self) -> str:
        return hidpp.feature_name(self.feature_id)


@dataclass
class DeviceInfo:
    product_id: int
    product_string: str
    serial: str
    short_path: bytes | None
    long_path: bytes | None


def find_devices(pids: set[int] = G502_HERO_PIDS) -> list[DeviceInfo]:
    found: dict[tuple, DeviceInfo] = {}
    for d in hid.enumerate(LOGITECH_VID):
        if d["product_id"] not in pids or d["usage_page"] != HIDPP_USAGE_PAGE:
            continue
        key = (d["product_id"], d.get("serial_number") or "", d["interface_number"])
        info = found.setdefault(
            key,
            DeviceInfo(d["product_id"], d.get("product_string") or "", d.get("serial_number") or "", None, None),
        )
        if d["usage"] == USAGE_SHORT:
            info.short_path = d["path"]
        elif d["usage"] == USAGE_LONG:
            info.long_path = d["path"]
    return [i for i in found.values() if i.long_path]


class Device:
    """A HID++ 2.0 device reached over wired USB (device index 0xFF)."""

    def __init__(self, info: DeviceInfo, device_index: int = hidpp.DEVICE_INDEX_WIRED):
        self.info = info
        self.device_index = device_index
        self._long = hid.device()
        self._long.open_path(info.long_path)
        self._short = None
        if info.short_path:
            self._short = hid.device()
            self._short.open_path(info.short_path)
        self.features: dict[int, FeatureInfo] = {}  # feature_id -> info
        self.protocol: tuple[int, int] | None = None

    @classmethod
    def open_first(cls) -> "Device":
        devices = find_devices()
        if not devices:
            raise DeviceNotFound("No G502 HERO found (VID 0x046D, PIDs %s)" % sorted(hex(p) for p in G502_HERO_PIDS))
        return cls(devices[0])

    def close(self) -> None:
        for h in (self._long, self._short):
            if h is not None:
                h.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- transport ---------------------------------------------------------

    def _drain(self) -> None:
        for h in (self._long, self._short):
            if h is None:
                continue
            h.set_nonblocking(1)
            while h.read(64):
                pass
            h.set_nonblocking(0)

    def _read_any(self, timeout_ms: int) -> bytes | None:
        """Read one report from the long handle, falling back to the short one."""
        data = self._long.read(64, timeout_ms)
        if data:
            return bytes(data)
        if self._short is not None:
            data = self._short.read(64, 1)
            if data:
                return bytes(data)
        return None

    def request(self, feature_index: int, function: int, params: bytes | list[int] = b"",
                timeout: float = DEFAULT_TIMEOUT) -> bytes:
        """Send a long HID++ 2.0 request and return the reply params (16 bytes)."""
        self._drain()
        msg = hidpp.build(feature_index, function, params, device_index=self.device_index)
        self._long.write(msg)
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            raw = self._read_any(max(1, int(remaining * 1000)))
            if raw is None:
                continue
            reply = hidpp.parse(raw)
            if reply is None or not hidpp.is_reply_to(reply, self.device_index, feature_index, function, hidpp.SW_ID):
                continue
            if reply.is_error:
                raise hidpp.HidppError(reply.params[1], feature_index, function)
            return reply.params
        raise TimeoutError(f"No reply to feature index 0x{feature_index:02X} function {function}")

    # -- Root / Feature Set ------------------------------------------------

    def ping(self) -> tuple[int, int]:
        """Root.ping: returns the HID++ protocol version (major, minor)."""
        r = self.request(0x00, 1, [0, 0, 0x5A])
        self.protocol = (r[0], r[1])
        return self.protocol

    def get_feature(self, feature_id: int) -> FeatureInfo | None:
        """Root.getFeature: resolve a feature ID to its index (None if absent)."""
        if feature_id in self.features:
            return self.features[feature_id]
        r = self.request(0x00, 0, [feature_id >> 8, feature_id & 0xFF])
        if r[0] == 0 and feature_id != 0x0000:
            return None
        info = FeatureInfo(feature_id, r[0], r[1], r[2])
        self.features[feature_id] = info
        return info

    def require(self, feature_id: int) -> int:
        info = self.get_feature(feature_id)
        if info is None:
            raise FeatureMissing(f"Device lacks feature 0x{feature_id:04X} ({hidpp.feature_name(feature_id)})")
        return info.index

    def list_features(self) -> list[FeatureInfo]:
        """Enumerate every feature via Feature Set (0x0001)."""
        fs = self.require(0x0001)
        count = self.request(fs, 0)[0]
        out = [FeatureInfo(0x0000, 0, 0, 0)]
        for i in range(1, count + 1):
            r = self.request(fs, 1, [i])
            info = FeatureInfo((r[0] << 8) | r[1], i, r[2], r[3])
            self.features.setdefault(info.feature_id, info)
            out.append(info)
        return out

    # -- simple info features ---------------------------------------------

    def get_name(self) -> str:
        idx = self.require(0x0005)
        length = self.request(idx, 0)[0]
        name = b""
        while len(name) < length:
            chunk = self.request(idx, 1, [len(name)])
            name += chunk[: length - len(name)]
        return name.decode("ascii", "replace")

    def get_firmware(self) -> list[dict]:
        """Device FW Version (0x0003): one entry per entity (bootloader, main fw...)."""
        info = self.get_feature(0x0003)
        if info is None:
            return []
        count = self.request(info.index, 0)[0]
        types = {0: "main", 1: "bootloader", 2: "hardware", 3: "touchpad", 4: "optical sensor"}
        out = []
        for e in range(count):
            r = self.request(info.index, 1, [e])
            prefix = r[1:4].decode("ascii", "replace").strip("\x00")
            out.append({
                "entity": e,
                "type": types.get(r[0] & 0x0F, f"0x{r[0]:02X}"),
                "version": f"{prefix}{r[4]:02X}.{r[5]:02X}.B{(r[6] << 8) | r[7]:04X}",
            })
        return out
