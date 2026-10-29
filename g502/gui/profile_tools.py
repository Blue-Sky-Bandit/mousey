"""Button tester, copy/swap/factory reset, the library, and JSON import/export."""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from .. import apply, library, model
from .common import APP_NAME, profile_subtitle, profile_title
from .tester import ButtonTesterDialog


class ToolsMixin:
    """Part of MainWindow; uses its state (self.edited, self.source, ...)."""

    def open_tester(self) -> None:
        if self.connected and self.active is not None:
            profile = next((p for p in self.original if p["sector"] == self.active), None)
            title = f"Profile {self.active}, as stored on the mouse"
        else:
            profile, title = None, ""
        if profile is None:
            profile = self.prof
            title = f"{profile_title(profile)} as shown in the editor (it may not be what's on the mouse)"
        ButtonTesterDialog(profile, title, self.tokens, self).exec()

    def _pick_profile(self, prompt: str) -> int | None:
        """Index into self.edited of another profile the user picks, or None."""
        others = [i for i in range(len(self.edited)) if i != self.sel]
        names = [profile_title(self.edited[i]) + (f" ({profile_subtitle(self.edited[i])})"
                                                  if profile_subtitle(self.edited[i]) else "") for i in others]
        choice, ok = QInputDialog.getItem(self, APP_NAME, prompt, names, 0, False)
        return others[names.index(choice)] if ok else None

    def _replace(self, index: int, new: dict) -> None:
        self.edited[index] = new

    def copy_profile(self) -> None:
        i = self._pick_profile(f"Copy {profile_title(self.prof)}'s settings to:")
        if i is None:
            return
        try:
            self._replace(i, library.load_into_slot(library.settings_of(self.prof), self.edited[i],
                                                    self.device["button_count"]))
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, f"Can't copy: {e}")
            return
        self._refresh_all()
        self.statusBar().showMessage(f"Copied {profile_title(self.prof)} to {profile_title(self.edited[i])}. "
                                     "Nothing is written until you press Write to mouse.", 8000)

    def swap_profile(self) -> None:
        i = self._pick_profile(f"Swap {profile_title(self.prof)} with:")
        if i is None:
            return
        mine, theirs = library.settings_of(self.prof), library.settings_of(self.edited[i])
        try:
            new_mine = library.load_into_slot(theirs, self.prof, self.device["button_count"])
            new_theirs = library.load_into_slot(mine, self.edited[i], self.device["button_count"])
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, f"Can't swap: {e}")
            return
        self._replace(self.sel, new_mine)
        self._replace(i, new_theirs)
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"Swapped {profile_title(self.prof)} and {profile_title(self.edited[i])}. "
                                     "Nothing is written until you press Write to mouse.", 8000)

    def factory_profiles(self) -> dict[int, dict]:
        """The mouse's factory default profiles (read-only memory), by number."""
        out = {}
        for n in range(1, 6):
            data = self.source.sectors.get(0x100 + n) if self.source else None
            if data:
                out[n] = model.decode_profile(data, self.device["button_count"])
        return out

    def reset_to_factory(self) -> None:
        factory = self.factory_profiles()
        if not factory:
            QMessageBox.information(self, APP_NAME, "The factory profiles weren't found in this data. "
                                                    "Read from the mouse first.")
            return
        names = [f"Factory profile {n}" for n in factory]
        default = min(max(self.prof["sector"] - 1, 0), len(names) - 1)
        choice, ok = QInputDialog.getItem(
            self, APP_NAME, f"Reset {profile_title(self.prof)} to which factory default?", names, default, False)
        if not ok:
            return
        n = list(factory)[names.index(choice)]
        new = dict(factory[n], sector=self.prof["sector"], enabled=self.prof.get("enabled", True))
        try:
            model.encode_profile({k: v for k, v in new.items() if k not in ("sector", "enabled")},
                                 self.device["button_count"])
        except ValueError as e:
            QMessageBox.warning(self, APP_NAME, f"Can't reset: {e}")
            return
        self._replace(self.sel, new)
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"{profile_title(new)} set to factory profile {n}, including its G-Shift "
                                     "layer and name. Nothing is written until you press Write to mouse.", 10000)

    def load_from_library(self, settings: dict, title: str) -> None:
        try:
            new = library.load_into_slot(settings, self.prof, self.device["button_count"])
        except (ValueError, KeyError, TypeError) as e:
            QMessageBox.warning(self, APP_NAME, f"\"{title}\" can't be loaded into this profile:\n\n{e}")
            return
        self.edited[self.sel] = new
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"Loaded \"{title}\" into {profile_title(new)}. Check it over, then "
                                     "press Write to mouse. Undo changes to this profile puts it back.", 10000)

    def save_to_library(self) -> None:
        p = self.prof
        default = profile_subtitle(p) or profile_title(p)
        title, ok = QInputDialog.getText(self, APP_NAME, "Name for this saved profile:", text=default)
        if not ok or not title.strip():
            return
        try:
            path = library.save_entry(self.library_dir, title.strip(), p)
        except (OSError, KeyError) as e:
            self._show_error(e)
            return
        self.library_page.reload()
        self.statusBar().showMessage(f"Saved \"{title.strip()}\" to the library ({path.name})", 6000)

    def delete_from_library(self, path: Path) -> None:
        if QMessageBox.question(self, APP_NAME, f"Delete the saved profile {path.name} from the library?\n"
                                                "This doesn't change the mouse.") != QMessageBox.Yes:
            return
        path.unlink(missing_ok=True)
        self.library_page.reload()

    def open_library_folder(self) -> None:
        self.library_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(self.library_dir)  # noqa: S606 - Windows only, opens Explorer

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export profiles", "g502-profiles.json", "JSON (*.json)")
        if not path:
            return
        doc = model.build_export(self.source)
        doc["profiles"] = self.edited
        Path(path).write_text(json.dumps(doc, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"Exported to {path}", 6000)

    def import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import profiles", "", "JSON (*.json)")
        if not path:
            return
        try:
            profiles = apply.load_profiles(Path(path))
            by_sector = {p["sector"]: p for p in self.edited}
            n = 0
            for p in profiles:
                dev = p.pop("_device", None)
                if dev and (dev.get("product_id"), dev.get("button_count")) != \
                        (self.device["product_id"], self.device["button_count"]):
                    raise ValueError("this file is for a different mouse")
                if p.get("sector") not in by_sector:
                    raise ValueError(f"profile {p.get('sector')} isn't on this mouse")
                try:
                    library.require_left_click(p)
                except ValueError as e:
                    raise ValueError(f"profile {p['sector']}: {e}") from None
                model.encode_profile({k: v for k, v in p.items() if k not in ("sector", "enabled")},
                                     self.device["button_count"],
                                     base=self.source.sectors[p["sector"]])
                p.setdefault("enabled", by_sector[p["sector"]].get("enabled", True))
                self.edited[self.edited.index(by_sector[p["sector"]])] = p
                n += 1
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, APP_NAME, f"Couldn't import that file:\n\n{e}")
            return
        self._show_profile()
        self._refresh_all()
        self.statusBar().showMessage(f"Imported {n} profile(s). Nothing is written until you press Write.", 8000)
