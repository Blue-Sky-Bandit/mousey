import json

import pytest

from g502 import model
from g502.backup import Backup

from .test_onboard import load_sectors

USER = [1, 2, 3, 4, 5]
ROM = [0x101, 0x102, 0x103, 0x104, 0x105]


def via_json(d):
    return json.loads(json.dumps(d))


@pytest.mark.parametrize("num", USER)
def test_user_profile_roundtrip_exact(num):
    data = load_sectors()[num]
    assert model.encode_profile(via_json(model.decode_profile(data))) == data


@pytest.mark.parametrize("num", ROM)
def test_factory_profile_roundtrip_exact(num):
    # ROM profiles carry no CRC (FF FF), so encode without one.
    data = load_sectors()[num]
    assert model.encode_profile(via_json(model.decode_profile(data)), with_crc=False) == data


def no_raw(obj):
    """No field fell back to raw hex: everything on this mouse is understood."""
    if isinstance(obj, dict):
        assert obj.get("type") != "raw" and obj.get("effect") != "raw" and "raw" not in obj, obj
        for v in obj.values():
            no_raw(v)
    elif isinstance(obj, list):
        for v in obj:
            no_raw(v)


@pytest.mark.parametrize("num", USER + ROM)
def test_everything_decodes_without_raw_fallback(num):
    no_raw(model.decode_profile(load_sectors()[num]))


def test_profile1_decode():
    p = model.decode_profile(load_sectors()[1])
    assert p["name"] == "PROFILE_NAME_DEFAULT"
    assert p["report_rate_hz"] == 1000
    assert p["dpi"] == {"levels": [1200, 2400, 3200, 3750, 6400], "default_index": 3, "shift_index": 0}
    b = p["buttons"]
    assert b["left"] == {"type": "mouse", "buttons": [1]}
    assert b["thumb_back"] == {"type": "key", "key": "v", "modifiers": ["lctrl"]}
    assert b["dpi_up"] == {"type": "key", "key": "tab", "modifiers": ["lgui"]}
    assert b["profile_switch"] == {"type": "special", "action": "profile_cycle"}
    assert p["gshift_buttons"]["left"] == {"type": "macro", "sector": 6, "offset": 0}
    assert p["lighting"]["logo_led"] == {"effect": "fixed", "color": "#FBC900"}


def test_factory_defaults_decode():
    p = model.decode_profile(load_sectors()[0x101])
    assert p["name"] is None
    assert [b.get("action") for b in p["buttons"].values()][5:] == [
        "dpi_shift", "dpi_down", "dpi_up", "profile_cycle", "wheel_right", "wheel_left"]
    assert p["lighting"]["logo_led"] == {"effect": "cycle", "period_ms": 8000, "brightness": 0}
    assert model.decode_profile(load_sectors()[0x102])["lighting"]["logo_led"] == {
        "effect": "breathing", "color": "#00DCFF", "period_ms": 8000, "waveform": 0, "brightness": 0}


def test_unknown_binding_kept_raw():
    data = bytearray(load_sectors()[3])
    data[0x20:0x24] = bytes([0x42, 0x01, 0x02, 0x03])
    data[0xFE:] = model.crc_ccitt(bytes(data[:0xFE])).to_bytes(2, "big")
    p = model.decode_profile(bytes(data))
    assert p["buttons"]["left"] == {"type": "raw", "hex": "42010203"}
    assert model.encode_profile(p) == bytes(data)


def test_edit_changes_only_intended_bytes():
    data = load_sectors()[3]
    p = model.decode_profile(data)
    p["dpi"]["levels"][0] = 800
    new = model.encode_profile(p)
    changed = [i for i in range(256) if new[i] != data[i]]
    assert changed == [3, 4, 0xFE, 0xFF]
    assert model.decode_profile(new)["dpi"]["levels"][0] == 800


@pytest.mark.parametrize("edit, msg", [
    (lambda p: p.update(report_rate_hz=300), "report rate"),
    (lambda p: p["dpi"].update(default_index=7), "default_index"),
    (lambda p: p["lighting"]["logo_led"].update(color="#12345"), "colour"),
    (lambda p: p["buttons"].pop("left"), "missing button"),
    (lambda p: p.update(name="x" * 25), "longer than 24"),
])
def test_invalid_values_rejected(edit, msg):
    p = model.decode_profile(load_sectors()[1])
    edit(p)
    with pytest.raises(ValueError, match=msg):
        model.encode_profile(p)


def test_export_document_roundtrip():
    meta = {"product_id": 0xC08B, "firmware": [{"version": "U1 27.03.B0010"}], "current_profile": 4,
            "onboard_info": {"button_count": 11, "profile_format_id": 2, "sector_size": 256, "sector_count": 16}}
    sectors = load_sectors()
    doc = via_json(model.build_export(Backup(meta, sectors), include_rom=True))
    assert [p["sector"] for p in doc["profiles"]] == USER
    for p in doc["profiles"]:
        assert model.encode_profile(p) == sectors[p["sector"]]
    assert any("sector 6, which is empty" in w for w in doc["warnings"])


def test_gshift_layer_derived_from_main_bindings():
    sectors = load_sectors()
    for num in range(1, 6):
        assert model.decode_profile(sectors[num])["gshift_layer"] is False
    p = model.decode_profile(sectors[3])
    p["buttons"]["sniper"] = {"type": "special", "action": "gshift"}
    p["gshift_layer"] = True
    assert model.decode_profile(model.encode_profile(p))["gshift_layer"] is True


@pytest.mark.parametrize("layer, sniper, msg", [
    (False, {"type": "special", "action": "gshift"}, "single-layer mode"),
    (True, {"type": "key", "key": "f"}, "unreachable"),
    ("no", {"type": "key", "key": "f"}, "true or false"),
])
def test_gshift_layer_validated(layer, sniper, msg):
    p = model.decode_profile(load_sectors()[3])
    p["gshift_layer"] = layer
    p["buttons"]["sniper"] = sniper
    with pytest.raises(ValueError, match=msg):
        model.encode_profile(p)


def test_single_layer_keeps_gshift_table_from_mouse():
    cur = load_sectors()[1]          # profile 1: G-Shift table points at macros in sector 6
    p = model.decode_profile(cur)
    p["gshift_layer"] = False
    p["buttons"]["sniper"] = {"type": "key", "key": "f"}
    del p["gshift_buttons"]
    new = model.encode_profile(p, base=cur)
    assert new[0x60:0xA0] == cur[0x60:0xA0]
    assert [i for i in range(256) if new[i] != cur[i]] == [0x35, 0x37, 0xFE, 0xFF] or \
        set(i for i in range(256) if new[i] != cur[i]) <= {0x34, 0x35, 0x36, 0x37, 0xFE, 0xFF}
    with pytest.raises(ValueError, match="gshift_buttons is missing"):
        model.encode_profile(p)
