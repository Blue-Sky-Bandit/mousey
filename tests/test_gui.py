"""Smoke test of the window against fixture data; never touches a device."""
import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from g502 import session  # noqa: E402
from g502.gui import app as gui  # noqa: E402
from g502.gui import style  # noqa: E402
from g502.gui.widgets import BindingDialog  # noqa: E402

from .test_apply import current  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(session, "read_mouse", lambda: pytest.fail("GUI test tried to read the device"))
    monkeypatch.setattr(session, "execute", lambda *a, **k: pytest.fail("GUI test tried to write"))
    w = gui.MainWindow(tmp_path, style.apply_theme(qapp, dark=True), library_dir=tmp_path / "library")
    w.load(current(), connected=False)
    return w


def test_loads_profiles(win):
    assert win.list.count() == 5
    assert win.changes_label.text() == "No unsaved changes"
    assert not win.write_btn.isEnabled()


def test_gshift_switch_assigns_and_restores_sniper(win):
    win.list.setCurrentRow(2)
    win.gshift_switch.setChecked(True)
    assert win.prof["buttons"]["sniper"] == {"type": "special", "action": "gshift"}
    assert win.table.isColumnHidden(2) is False
    win.gshift_switch.setChecked(False)
    assert win.prof == win.orig
    assert win.table.isColumnHidden(2)


def test_edits_mark_profile_and_plan(win):
    win.list.setCurrentRow(2)
    win.leds["logo_led"].effect.setCurrentIndex(win.leds["logo_led"].effect.findData("off"))
    assert win.prof["lighting"]["logo_led"] == {"effect": "off"}
    assert win.write_btn.isEnabled()
    plan = session.plan_profiles(win.edited, win.original, win.source, win.device)
    assert plan.order == [3]
    win.revert_profile()
    assert win.edited == win.original


def test_dpi_editor_roundtrip(win):
    win.list.setCurrentRow(2)
    before = win.prof["dpi"]
    win.dpi.rows[1][1].setValue(1800)
    assert win.prof["dpi"]["levels"][1] == 1800
    assert win.prof["dpi"]["default_index"] == before["default_index"]


def test_binding_dialog_result(win):
    d = BindingDialog("thumb_back", "main", {"type": "mouse", "buttons": [4]}, False, win)
    assert d.category.findData("gshift") < 0
    d.category.setCurrentIndex(d.category.findData("key"))
    d.key.setCurrentIndex(d.key.findData("v"))
    d.mods["lctrl"].setChecked(True)
    assert d.result_binding() == {"type": "key", "key": "v", "modifiers": ["lctrl"]}


def test_live_tracking_follows_profile_and_unplug(win):
    from g502.device import DeviceNotFound
    win.load(current(), connected=True)
    win.poll_timer.stop()
    win._poll_done(session.Status(2, "onboard"))
    assert win.active == 2
    win._poll_failed(DeviceNotFound("gone"))
    assert not win.connected and not win.plugged
    assert "unplugged" in win.status_pill.text()
    win.prof["name"] = "edited"                 # unsaved edits: no automatic re-read
    win._poll_done(session.Status(3, "onboard"))
    assert win.plugged and not win.connected


def test_in_use_profile_cannot_be_deactivated(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: shown.append(a[2]))
    win.load(current(), connected=True)
    win.poll_timer.stop()
    win.active = 3
    win.list.setCurrentRow(2)
    win.enabled.setChecked(False)
    assert win.prof["enabled"] is True and "in use" in shown[-1]
    win.list.setCurrentRow(4)
    win.enabled.setChecked(False)
    assert win.prof["enabled"] is False


def test_library_load_and_save(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    from g502 import library
    assert win.library_page.saved_buttons == []          # nothing pre-populated
    win.list.setCurrentRow(0)
    entry = library.settings_of(dict(win.prof, name="Mine", lighting={
        "logo_led": {"effect": "fixed", "color": "#00FF00"}, "dpi_leds": {"effect": "off"}}))
    win.list.setCurrentRow(2)
    win.load_from_library(entry, "Mine")
    assert win.prof["name"] == "Mine" and win.prof["sector"] == 3
    assert win.write_btn.isEnabled()
    plan = session.plan_profiles(win.edited, win.original, win.source, win.device)
    assert plan.order == [3]
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("My FPS", True))
    win.save_to_library()
    assert len(list(win.library_dir.glob("*.json"))) == 1
    assert win.library_page.saved_buttons[0].text() == "Load into Profile 3"


def test_left_click_locked_on_main_layer(win, monkeypatch):
    from g502.gui import editor as appmod
    opened = []
    monkeypatch.setattr(appmod, "BindingDialog", lambda *a, **k: opened.append(a) or pytest.fail("opened"))
    win.list.setCurrentRow(2)
    win._edit_binding(0, 1)
    assert not opened and "🔒" in win.table.item(0, 1).text()
    assert win.prof["buttons"]["left"] == {"type": "mouse", "buttons": [1]}


def test_mode_guard_banner(win):
    from g502.backup import Backup
    b = current()
    win.load(Backup(dict(b.meta, onboard_mode="host"), b.sectors), connected=True)
    win.poll_timer.stop()
    assert win.mode == "host" and win.mode_holder.count() == 1
    win._poll_done(session.Status(4, "onboard"))
    assert win.mode == "onboard" and win.mode_holder.count() == 0


def test_copy_swap_and_factory_reset(win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    win.list.setCurrentRow(0)                      # profile 1 (yellow)
    p1, p5 = win.edited[0], win.edited[4]
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (a[3][-1], True))   # last choice
    win.swap_profile()
    assert win.edited[0]["lighting"] == p5["lighting"] and win.edited[4]["lighting"] == p1["lighting"]
    assert win.edited[0]["sector"] == 1 and win.edited[4]["sector"] == 5
    assert win.edited[0]["gshift_buttons"] == p1["gshift_buttons"]          # hidden table stays put
    win.edited = [dict(p) for p in win.original]
    win.copy_profile()
    assert win.edited[4]["lighting"] == win.original[0]["lighting"]
    plan = session.plan_profiles(win.edited, win.original, win.source, win.device)
    assert plan.order == [5]
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: (a[3][2], True))    # factory profile 3
    win.reset_to_factory()
    assert win.prof["name"] is None and win.prof["sector"] == 1
    assert win.prof["buttons"]["left"] == {"type": "mouse", "buttons": [1]}


def test_tester_matches_inputs(qapp):
    from g502 import model
    from g502.gui.tester import rows_for, same_action
    p = model.decode_profile(current().sectors[3])
    rows = rows_for(p)
    assert len(rows) == 11
    assert same_action({"type": "key", "key": "v", "modifiers": ["rctrl"]},
                       {"type": "key", "key": "v", "modifiers": ["lctrl"]})
    assert not same_action({"type": "key", "key": "v"}, {"type": "key", "key": "v", "modifiers": ["lctrl"]})
    hits = [r for r, (_, _, b) in enumerate(rows) if same_action(b, {"type": "mouse", "buttons": [2]})]
    assert [rows[r][0] for r in hits] == ["Right click"]


def test_tester_dialog_opens(win):
    from g502.gui.tester import ButtonTesterDialog
    d = ButtonTesterDialog(win.prof, "Profile 3", win.tokens, win)
    d._received({"type": "mouse", "buttons": [2]})
    assert d.table.item(1, 2).text() == "✓"
    assert "Right click" in d.log.item(0).text()


def test_splash_plays_once_and_waits_for_loading(qapp):
    from g502.gui.splash import Splash
    s = Splash()
    assert s.movie.isValid() and s.frames == 120
    done = []
    s.finished.connect(lambda: done.append(True))
    s._frame(s.frames - 1)                     # animation reached its last frame
    assert s.played and not s.loaded and s.progress() <= 0.92
    s.set_loaded("Ready")
    assert s.loaded and s.status == "Ready"


def test_tester_follows_profile_in_use(win):
    from g502.gui.tester import ButtonTesterDialog
    win.load(current(), connected=True)
    win.poll_timer.stop()
    win._poll_done(session.Status(2, "onboard"))
    win.tester = ButtonTesterDialog(*win._tester_profile(), win.tokens, win)
    assert "Profile 2" in win.tester.testing.text()
    win.tester._received({"type": "mouse", "buttons": [2]})
    win._poll_done(session.Status(3, "onboard"))
    assert "Profile 3" in win.tester.testing.text()
    assert win.tester.table.item(1, 2).text() == ""            # ticks start again
    assert "Now testing Profile 3" in win.tester.log.item(0).text()


def test_keys_read_by_position_not_layout(qapp):
    from g502.gui.widgets import key_from_event

    class Event:                                # what Qt reports on a UK layout
        def __init__(self, scan, vk):
            self.scan, self.vk = scan, vk

        def nativeScanCode(self):
            return self.scan

        def nativeVirtualKey(self):
            return self.vk

        def key(self):
            return 0
    assert key_from_event(Event(0x2B, 0xDE)) == "backslash"      # UK # key: VK says apostrophe
    assert key_from_event(Event(0x28, 0xC0)) == "apostrophe"     # UK ' key: VK says grave
    assert key_from_event(Event(0xE048, 0x26)) == "up"
    assert key_from_event(Event(0x45, 0x90)) == "num_lock"
    assert key_from_event(Event(0x1D, 0xA2)) is None             # modifiers alone aren't keys


def test_key_labels_follow_layout():
    from g502 import labels
    before = labels.key_label("backslash")
    try:
        labels.use_layout({"backslash": "#", "slash": ""})
        assert labels.key_label("backslash") == "#"
        assert labels.key_label("slash") == "/"
    finally:
        labels.use_layout({"backslash": before})


def test_waiting_page_without_mouse_or_backups(qapp, tmp_path, monkeypatch):
    from g502.device import DeviceNotFound
    from g502.gui import device_ops
    monkeypatch.setenv("APPDATA", str(tmp_path))               # no older folders with backups either
    monkeypatch.setattr(device_ops, "QMessageBox", None)       # no pop-up expected
    monkeypatch.setattr(gui, "QMessageBox", None)
    w = gui.MainWindow(tmp_path / "empty", style.apply_theme(qapp, dark=True), library_dir=tmp_path / "library")
    assert w.pages.currentIndex() == 0
    w._read_failed(DeviceNotFound("none"))
    w.poll_timer.stop()
    assert w.pages.currentIndex() == 0 and "Waiting" in w.statusBar().currentMessage()
    w.load(current(), connected=False)
    assert w.pages.currentIndex() == 1
