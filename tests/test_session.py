import copy

import pytest

from g502 import labels, model, session
from g502.backup import Backup

from .test_apply import META, current


def profiles():
    doc = model.build_export(current())
    return doc["device"], doc["profiles"]


def test_no_edits_plans_nothing():
    device, original = profiles()
    plan = session.plan_profiles(copy.deepcopy(original), original, current(), device)
    assert plan.empty


def test_plan_describes_what_is_written():
    device, original = profiles()
    edited = copy.deepcopy(original)
    p = edited[2]
    p["buttons"]["sniper"] = {"type": "special", "action": "gshift"}
    p["gshift_layer"] = True
    p["gshift_buttons"]["thumb_forward"] = {"type": "key", "key": "c", "modifiers": ["lctrl"]}
    p["lighting"]["logo_led"] = {"effect": "fixed", "color": "#FF3366"}
    plan = session.plan_profiles(edited, original, current(), device)
    assert plan.order == [3]
    rows = session.describe_plan(plan, 11)
    assert ("Profile 3", "Buttons", "Sniper button", "DPI shift (sniper)", "G-Shift") in rows
    assert ("Profile 3", "G-Shift layer", "Thumb forward", "Forward", "Ctrl+C") in rows
    assert ("Profile 3", "Lighting", "Logo", "Colour cycle, 8 s, brightness 100%", "Solid #FF3366") in rows


def test_disabling_a_profile_writes_the_directory_last():
    device, original = profiles()
    edited = copy.deepcopy(original)
    edited[4]["enabled"] = False
    plan = session.plan_profiles(edited, original, current(), device)
    assert plan.order == [0]
    assert session.describe_plan(plan, 11) == [
        ("Profile list", "Profiles", "Profile 5", "Active", "Deactivated")]


def test_restore_plan_refuses_other_firmware():
    other = Backup(dict(META, firmware=[{"version": "U1 99.99"}]), current().sectors)
    with pytest.raises(ValueError, match="can't be restored"):
        session.plan_backup_restore(other, current())


def test_labels():
    assert labels.describe_binding({"type": "key", "key": "f13", "modifiers": ["lshift"]}) == "Shift+F13"
    assert labels.describe_binding({"type": "consumer", "usage": "0x00E9"}) == "Volume up"
    assert labels.describe_binding({"type": "mouse", "buttons": [4]}) == "Back"
    assert set(labels.BUTTON_LABELS) == set(model.BUTTON_NAMES)
    assert set(labels.ZONE_LABELS) == set(model.LED_ZONES)
    assert all(n in model.KEY_CODES for n in labels.key_names_sorted())


def test_read_retries_once_after_timeout(monkeypatch):
    calls = []

    def fake():
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError("still starting")
        return "backup"
    monkeypatch.setattr(session, "_read", fake)
    assert session.read_mouse(retry_delay=0) == "backup"
    assert len(calls) == 2


def test_diagnostics_report_has_no_profile_contents(tmp_path):
    from g502 import diagnostics
    text = diagnostics.report(current(), True, ["2026-10-30 boom"], tmp_path, tmp_path)
    assert "sector 0x0003: crc-ok" in text and "boom" in text
    assert current().sectors[3].hex() not in text      # no raw profile data
