import copy
import json

import pytest

from g502 import apply, model
from g502.backup import Backup
from g502.onboard import parse_directory

from .test_onboard import load_sectors

META = {"product_id": 0xC08B, "firmware": [{"version": "U1 27.03.B0010"}], "current_profile": 4,
        "onboard_info": {"button_count": 11, "profile_format_id": 2, "sector_size": 256, "sector_count": 16}}


def current() -> Backup:
    return Backup(META, load_sectors())


def export_profiles(tmp_path, edit=None):
    doc = json.loads(json.dumps(model.build_export(current())))
    if edit:
        edit(doc)
    path = tmp_path / "p.json"
    path.write_text(json.dumps(doc))
    return apply.load_profiles(path)


def by_sector(profiles, s):
    return next(p for p in profiles if p["sector"] == s)


def test_unchanged_export_plans_nothing(tmp_path):
    plan = apply.plan_apply(export_profiles(tmp_path), current(), [1, 2, 3, 4, 5])
    assert plan.sectors == {} and plan.notes == []


def test_led_change_only_touches_named_sector(tmp_path):
    profiles = export_profiles(tmp_path)
    for p in profiles:
        p["lighting"]["logo_led"] = {"effect": "fixed", "color": "#FF0000"}
    plan = apply.plan_apply(profiles, current(), [3])
    assert list(plan.sectors) == [3]
    old = load_sectors()[3]
    changed = [i for i in range(256) if plan.sectors[3][i] != old[i]]
    # cycle 03 00 00 00 00 00 1F 40 64 -> fixed 01 FF 00 00 ...: mode, red, period, brightness
    assert changed == [0xD0, 0xD1, 0xD6, 0xD7, 0xD8, 0xFE, 0xFF]
    assert "lighting.logo_led: 'cycle period_ms=8000 brightness=100' -> 'fixed color=#FF0000'" in plan.field_diffs[3]


def test_refuses_sector_not_in_directory_and_directory_itself(tmp_path):
    profiles = export_profiles(tmp_path)
    p6 = copy.deepcopy(by_sector(profiles, 3))
    p6["sector"] = 6
    with pytest.raises(ValueError, match="not a profile in the mouse's directory"):
        apply.plan_apply(profiles + [p6], current(), [6])
    with pytest.raises(ValueError, match="directory is not a profile"):
        apply.plan_apply(profiles, current(), [0])
    with pytest.raises(ValueError, match="not in the profile file"):
        apply.plan_apply([by_sector(profiles, 3)], current(), [2])


def test_invalid_value_reports_sector(tmp_path):
    profiles = export_profiles(tmp_path)
    by_sector(profiles, 3)["dpi"]["levels"] = [100, 200, 300, 400, 500, 600]
    with pytest.raises(ValueError, match="sector 3: at most 5 DPI levels"):
        apply.plan_apply(profiles, current(), [3])
    del by_sector(profiles, 3)["dpi"]
    with pytest.raises(ValueError, match="sector 3: missing or malformed"):
        apply.plan_apply(profiles, current(), [3])


def test_wrong_device_rejected(tmp_path):
    profiles = export_profiles(tmp_path, lambda d: d["device"].update(button_count=9))
    with pytest.raises(ValueError, match="button_count"):
        apply.plan_apply(profiles, current(), [3])


def test_enable_flag_needs_directory_flag(tmp_path):
    profiles = export_profiles(tmp_path)
    by_sector(profiles, 5)["enabled"] = False
    plan = apply.plan_apply(profiles, current(), [5])
    assert plan.sectors == {} and "ignored" in plan.notes[0]
    plan = apply.plan_apply(profiles, current(), [5], directory=True)
    assert plan.order == [0]
    entries = {e.sector: e.enabled for e in parse_directory(plan.sectors[0])}
    assert entries == {1: True, 2: True, 3: True, 4: True, 5: False}
    for p in profiles:
        p["enabled"] = False
    with pytest.raises(ValueError, match="every profile"):
        apply.plan_apply(profiles, current(), [1, 2, 3, 4, 5], directory=True)


def test_single_profile_file(tmp_path):
    p = by_sector(export_profiles(tmp_path), 3)
    p.pop("_device")
    p["name"] = "Test"
    path = tmp_path / "one.json"
    path.write_text(json.dumps(p))
    plan = apply.plan_apply(apply.load_profiles(path), current(), [3])
    assert plan.order == [3] and "name: 'PROFILE_NAME_DEFAULT' -> 'Test'" in plan.field_diffs[3]


def test_single_layer_profile_plans_only_the_rebound_button(tmp_path):
    def edit(doc):
        p = next(x for x in doc["profiles"] if x["sector"] == 1)
        p["gshift_layer"] = False
        p["buttons"]["sniper"] = {"type": "key", "key": "f"}
        del p["gshift_buttons"]
    plan = apply.plan_apply(export_profiles(tmp_path, edit), current(), [1])
    old, new = current().sectors[1], plan.sectors[1]
    assert {i for i in range(256) if old[i] != new[i]} <= {0x34, 0x35, 0x36, 0x37, 0xFE, 0xFF}
    assert new[0x60:0xA0] == old[0x60:0xA0]
    assert plan.field_diffs[1] == ["buttons.sniper: 'key enter' -> 'key f'"]


def test_old_export_version_rejected(tmp_path):
    with pytest.raises(ValueError, match="re-export"):
        export_profiles(tmp_path, lambda doc: doc.update(format_version=1))
