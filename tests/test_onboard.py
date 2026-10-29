import json
from pathlib import Path

from g502 import hidpp
from g502.onboard import crc_ccitt, parse_directory, sector_crc_ok

FIXTURE = Path(__file__).parent / "fixtures" / "g502_dump_initial.json"


def load_sectors() -> dict[int, bytes]:
    data = json.loads(FIXTURE.read_text())
    return {int(k, 16): bytes.fromhex(v) for k, v in data["sectors"].items() if v}


def test_crc_known_vector():
    # CRC-16/CCITT-FALSE check value
    assert crc_ccitt(b"123456789") == 0x29B1


def test_user_sectors_crc_match_device():
    sectors = load_sectors()
    for num in range(0x0000, 0x0006):
        assert sector_crc_ok(sectors[num]), f"sector 0x{num:04X}"


def test_directory_parse():
    entries = parse_directory(load_sectors()[0x0000])
    assert [e.sector for e in entries] == [1, 2, 3, 4, 5]
    assert all(e.enabled for e in entries)


def test_build_and_match_reply():
    req = hidpp.build(0x0C, 5, [0, 1, 0, 0x10])
    assert len(req) == 20 and req[:4] == bytes([0x11, 0xFF, 0x0C, 0x5B])
    reply = hidpp.parse(bytes([0x11, 0xFF, 0x0C, 0x5B]) + bytes(16))
    assert hidpp.is_reply_to(reply, 0xFF, 0x0C, 5, hidpp.SW_ID)
    err = hidpp.parse(bytes([0x11, 0xFF, 0xFF, 0x0C, 0x5B, 0x02]) + bytes(14))
    assert err.is_error and hidpp.is_reply_to(err, 0xFF, 0x0C, 5, hidpp.SW_ID)
