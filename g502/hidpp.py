"""HID++ 2.0 message building and parsing.

Message layout (both report types):
    [report_id, device_index, feature_index, (function << 4) | sw_id, params...]

Short reports are 7 bytes (ID 0x10), long reports 20 bytes (ID 0x11).
An error reply is [report_id, device_index, 0xFF, orig_feature_index,
orig_func_sw, error_code, ...].
"""

from __future__ import annotations

from dataclasses import dataclass

REPORT_SHORT = 0x10
REPORT_LONG = 0x11
REPORT_LEN = {REPORT_SHORT: 7, REPORT_LONG: 20}

DEVICE_INDEX_WIRED = 0xFF

# Software ID put in the low nibble of byte 3; non-zero so we can tell our
# replies apart from unsolicited device notifications (sw_id 0).
SW_ID = 0x0B

ERROR_FEATURE_INDEX = 0xFF
HIDPP10_ERROR = 0x8F

HIDPP20_ERRORS = {
    0x00: "NoError",
    0x01: "Unknown",
    0x02: "InvalidArgument",
    0x03: "OutOfRange",
    0x04: "HardwareError",
    0x05: "LogitechInternal",
    0x06: "InvalidFeatureIndex",
    0x07: "InvalidFunctionId",
    0x08: "Busy",
    0x09: "Unsupported",
}

# Feature IDs we care about. Indexes are always resolved at runtime via Root.
FEATURE_NAMES = {
    0x0000: "Root",
    0x0001: "Feature Set",
    0x0002: "Feature Info",
    0x0003: "Device FW Version",
    0x0005: "Device Name",
    0x0020: "Config Change",
    0x00C2: "DFU Control",
    0x1300: "LED Control",
    0x1801: "Manufacturing Mode",
    0x1000: "Battery Status",
    0x1D4B: "Wireless Device Status",
    0x1E00: "Enable Hidden Features",
    0x1EB0: "TDE Access",
    0x1802: "Device Reset",
    0x1803: "GPIO Access",
    0x1806: "Device Config",
    0x1811: "OOB State",
    0x1830: "Power Modes",
    0x1890: "RF Test",
    0x18A1: "LED Test",
    0x18B1: "Monitor Mode",
    0x1891: "RF Test 2",
    0x1DF3: "Equad DJ Debug",
    0x1E22: "SPI Direct Access",
    0x2201: "Adjustable DPI",
    0x2202: "Extended Adjustable DPI",
    0x2250: "Analysis Mode",
    0x8060: "Report Rate",
    0x8061: "Extended Report Rate",
    0x8070: "Color LED Effects",
    0x8071: "RGB Effects",
    0x8081: "Per-Key Lighting v2",
    0x8090: "Mode Status",
    0x8100: "Onboard Profiles",
    0x8110: "Mouse Button Spy",
    0x8111: "Latency Monitoring",
}


def feature_name(feature_id: int) -> str:
    return FEATURE_NAMES.get(feature_id, "unknown")


class HidppError(Exception):
    """Device returned an HID++ error reply."""

    def __init__(self, code: int, feature_index: int, function: int):
        self.code = code
        self.feature_index = feature_index
        self.function = function
        name = HIDPP20_ERRORS.get(code, f"0x{code:02X}")
        super().__init__(
            f"HID++ error {name} (feature index 0x{feature_index:02X}, function {function})"
        )


@dataclass(frozen=True)
class Message:
    report_id: int
    device_index: int
    feature_index: int
    function: int
    sw_id: int
    params: bytes

    @property
    def is_error(self) -> bool:
        return self.feature_index in (ERROR_FEATURE_INDEX, HIDPP10_ERROR)


def build(
    feature_index: int,
    function: int,
    params: bytes | list[int] = b"",
    *,
    device_index: int = DEVICE_INDEX_WIRED,
    report_id: int = REPORT_LONG,
    sw_id: int = SW_ID,
) -> bytes:
    length = REPORT_LEN[report_id]
    params = bytes(params)
    if len(params) > length - 4:
        raise ValueError(f"too many params ({len(params)}) for report 0x{report_id:02X}")
    if not 0 <= function <= 0x0F:
        raise ValueError(f"function {function} out of range")
    head = bytes([report_id, device_index, feature_index, (function << 4) | (sw_id & 0x0F)])
    return (head + params).ljust(length, b"\x00")


def parse(data: bytes | list[int]) -> Message | None:
    data = bytes(data)
    if len(data) < 4 or data[0] not in REPORT_LEN:
        return None
    return Message(
        report_id=data[0],
        device_index=data[1],
        feature_index=data[2],
        function=data[3] >> 4,
        sw_id=data[3] & 0x0F,
        params=data[4:],
    )


def is_reply_to(msg: Message, device_index: int, feature_index: int, function: int, sw_id: int) -> bool:
    """True if msg is the reply (or error reply) to the given request."""
    if msg.device_index != device_index:
        return False
    if msg.is_error:
        # Error replies (2.0 and 1.0 alike): byte 3 is the original feature
        # index / sub-id, byte 4 the original function|sw_id, byte 5 the code.
        orig_feature_index = (msg.function << 4) | msg.sw_id
        return orig_feature_index == feature_index and msg.params[0] == ((function << 4) | sw_id)
    return msg.feature_index == feature_index and msg.function == function and msg.sw_id == sw_id
