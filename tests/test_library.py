import copy

import pytest

from g502 import library, model

from .test_apply import current


def slots():
    return model.build_export(current())["profiles"]


def custom():
    """A user-made single-layer profile, as saved to the library."""
    p = copy.deepcopy(slots()[2])
    p["name"] = "Custom"
    p["dpi"] = {"levels": [400, 800, 1600], "default_index": 1, "shift_index": 0}
    p["buttons"]["thumb_back"] = {"type": "key", "key": "v"}
    p["lighting"]["logo_led"] = {"effect": "fixed", "color": "#123456"}
    return library.settings_of(p)


def test_entry_loads_into_any_slot():
    for slot in slots():
        new = library.load_into_slot(custom(), slot)
        assert new["sector"] == slot["sector"] and new["enabled"] == slot["enabled"]
        assert new["advanced"] == slot["advanced"]
        assert new["gshift_buttons"] == slot["gshift_buttons"]   # hidden table untouched
        assert new["name"] == "Custom" and new["dpi"]["levels"] == [400, 800, 1600]


def test_single_layer_load_keeps_hidden_gshift_bytes():
    slot = slots()[0]                     # profile 1: G-Shift table holds macro references
    new = library.load_into_slot(custom(), slot)
    enc = model.encode_profile({k: v for k, v in new.items() if k not in ("sector", "enabled")})
    assert enc[0x60:0xA0] == current().sectors[1][0x60:0xA0]


def test_gshift_layer_entry_carries_its_table():
    p = copy.deepcopy(slots()[2])
    p["buttons"]["sniper"] = {"type": "special", "action": "gshift"}
    p["gshift_buttons"]["thumb_back"] = {"type": "key", "key": "7"}
    s = library.settings_of(p)
    assert s["gshift_layer"] is True
    new = library.load_into_slot(s, slots()[0])
    assert new["gshift_buttons"]["thumb_back"] == {"type": "key", "key": "7"}


def test_save_and_load_roundtrip(tmp_path):
    slot = copy.deepcopy(slots()[2])
    slot["lighting"]["logo_led"] = {"effect": "fixed", "color": "#123456"}
    path = library.save_entry(tmp_path, "My FPS", slot, "test")
    entries, problems = library.list_entries(tmp_path)
    assert not problems and len(entries) == 1 and entries[0].path == path
    e = entries[0]
    assert e.title == "My FPS" and e.profile["lighting"]["logo_led"]["color"] == "#123456"
    assert "sector" not in e.profile and "advanced" not in e.profile
    new = library.load_into_slot(e.profile, slots()[4])
    assert new["lighting"] == slot["lighting"] and new["sector"] == 5


def test_bad_files_reported_not_fatal(tmp_path):
    (tmp_path / "junk.json").write_text("{}", encoding="utf-8")
    entries, problems = library.list_entries(tmp_path)
    assert entries == [] and "junk.json" in problems[0]


def test_invalid_entry_refused():
    bad = custom()
    bad["dpi"]["default_index"] = 9
    with pytest.raises(ValueError):
        library.load_into_slot(bad, slots()[0])


def test_entry_without_left_click_refused():
    bad = custom()
    bad["buttons"]["left"] = {"type": "key", "key": "a"}
    with pytest.raises(ValueError, match="Left click"):
        library.load_into_slot(bad, slots()[0])
