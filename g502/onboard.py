"""Onboard Profiles feature (0x8100): info, sector reads, CRC, directory.

Layout and function numbers follow libratbag (src/hidpp20.c). This module is
read-only for now; write support comes after backup/restore is proven.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .device import Device
from .hidpp import HidppError

FEATURE_ONBOARD_PROFILES = 0x8100

# Function numbers (libratbag CMD_ONBOARD_PROFILES_* >> 4)
FN_GET_PROFILES_DESCR = 0x0
FN_SET_ONBOARD_MODE = 0x1
FN_GET_ONBOARD_MODE = 0x2
FN_SET_CURRENT_PROFILE = 0x3
FN_GET_CURRENT_PROFILE = 0x4
FN_MEMORY_READ = 0x5
FN_MEMORY_ADDR_WRITE = 0x6
FN_MEMORY_WRITE = 0x7
FN_MEMORY_WRITE_END = 0x8
FN_GET_CURRENT_DPI_INDEX = 0xB
FN_SET_CURRENT_DPI_INDEX = 0xC

ONBOARD_MODES = {1: "onboard", 2: "host"}

# Sector 0x0000 is the user profile directory; 0x0001.. are user profiles.
# Factory (read-only) sectors start at 0x0100.
SECTOR_DIRECTORY = 0x0000
ROM_SECTOR_BASE = 0x0100

READ_CHUNK = 16
WRITE_END_TIMEOUT = 5.0  # flash commit can be slower than a normal request


def is_blank(sector: bytes) -> bool:
    """Erased (all FF) or unbacked (all 00) sector: carries no CRC."""
    return all(b == 0xFF for b in sector) or all(b == 0x00 for b in sector)


@dataclass
class OnboardInfo:
    memory_model_id: int
    profile_format_id: int
    macro_format_id: int
    profile_count: int
    profile_count_oob: int
    button_count: int
    sector_count: int
    sector_size: int
    mechanical_layout: int
    various_info: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DirectoryEntry:
    sector: int
    enabled: bool
    raw: bytes


def crc_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), as used by libratbag."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


def sector_crc_ok(sector: bytes) -> bool:
    stored = int.from_bytes(sector[-2:], "big")
    return crc_ccitt(sector[:-2]) == stored


def parse_directory(sector: bytes) -> list[DirectoryEntry]:
    """Directory is a list of 4-byte entries [sector_hi, sector_lo, enabled, 0]
    terminated by sector 0xFFFF."""
    entries = []
    for off in range(0, len(sector) - 2, 4):
        raw = sector[off:off + 4]
        num = int.from_bytes(raw[0:2], "big")
        if num == 0xFFFF:
            break
        entries.append(DirectoryEntry(num, raw[2] != 0, raw))
    return entries


class OnboardProfiles:
    def __init__(self, dev: Device):
        self.dev = dev
        self.index = dev.require(FEATURE_ONBOARD_PROFILES)
        self.info = self._get_info()

    def _get_info(self) -> OnboardInfo:
        r = self.dev.request(self.index, FN_GET_PROFILES_DESCR)
        return OnboardInfo(
            memory_model_id=r[0],
            profile_format_id=r[1],
            macro_format_id=r[2],
            profile_count=r[3],
            profile_count_oob=r[4],
            button_count=r[5],
            sector_count=r[6],
            sector_size=int.from_bytes(r[7:9], "big"),
            mechanical_layout=r[9],
            various_info=r[10],
        )

    def get_mode(self) -> str:
        m = self.dev.request(self.index, FN_GET_ONBOARD_MODE)[0]
        return ONBOARD_MODES.get(m, f"0x{m:02X}")

    def set_mode(self, mode: str) -> None:
        """Switch between 'onboard' (the mouse runs its stored profiles) and 'host'
        (software controls it). Not a memory write; nothing stored is changed."""
        code = {v: k for k, v in ONBOARD_MODES.items()}[mode]
        self.dev.request(self.index, FN_SET_ONBOARD_MODE, [code])

    def get_current_profile(self) -> int:
        r = self.dev.request(self.index, FN_GET_CURRENT_PROFILE)
        return int.from_bytes(r[0:2], "big")

    def get_current_dpi_index(self) -> int:
        return self.dev.request(self.index, FN_GET_CURRENT_DPI_INDEX)[0]

    def read_memory(self, sector: int, offset: int) -> bytes:
        r = self.dev.request(self.index, FN_MEMORY_READ, [sector >> 8, sector & 0xFF, offset >> 8, offset & 0xFF])
        return bytes(r[:READ_CHUNK])

    def read_sector(self, sector: int) -> bytes:
        size = self.info.sector_size
        buf = bytearray(size)
        for off in range(0, size, READ_CHUNK):
            # The device rejects reads that run past the sector end, so the
            # last chunk is read aligned to the end (libratbag does the same).
            start = min(off, size - READ_CHUNK)
            buf[start:start + READ_CHUNK] = self.read_memory(sector, start)
        return bytes(buf)

    def rom_sectors(self, limit: int = 0x40) -> list[int]:
        """Factory sectors that answer a read, probed from 0x0100 upwards."""
        found = []
        for s in range(ROM_SECTOR_BASE, ROM_SECTOR_BASE + limit):
            try:
                self.read_memory(s, 0)
            except HidppError:
                break
            found.append(s)
        return found

    def write_sector(self, sector: int, data: bytes) -> None:
        """Write one whole user sector, bytes exactly as given (CRC included).

        Sequence per libratbag: MEMORY_ADDR_WRITE(sector, offset 0, length),
        MEMORY_WRITE in 16-byte chunks, MEMORY_WRITE_END. No retries: an error
        mid-way propagates and the sector may be partially written."""
        size = self.info.sector_size
        if len(data) != size:
            raise ValueError(f"sector data is {len(data)} bytes, expected {size}")
        if not 0 <= sector < self.info.sector_count:
            raise ValueError(f"refusing to write sector 0x{sector:04X}: not a user sector")
        self.dev.request(self.index, FN_MEMORY_ADDR_WRITE,
                         [sector >> 8, sector & 0xFF, 0, 0, size >> 8, size & 0xFF])
        for off in range(0, size, READ_CHUNK):
            self.dev.request(self.index, FN_MEMORY_WRITE, data[off:off + READ_CHUNK])
        self.dev.request(self.index, FN_MEMORY_WRITE_END, timeout=WRITE_END_TIMEOUT)
