import copy

from g502 import backup, model, timeline

from .test_apply import META, current


def save(tmp_path, b, stamp, reason=None):
    b = backup.Backup(dict(b.meta, created=f"2026-10-30T{stamp}.000000", backup_format=backup.BACKUP_FORMAT),
                      dict(b.sectors))
    return backup.save_backup(b, tmp_path, reason)


def test_timeline_describes_changes_and_matches(tmp_path):
    first = current()
    p = model.decode_profile(first.sectors[3])
    p["lighting"]["logo_led"] = {"effect": "fixed", "color": "#FF00FF"}
    second = backup.Backup(META, {**first.sectors, 3: model.encode_profile(p)})
    third = backup.Backup(META, copy.deepcopy(second.sectors))
    paths = [save(tmp_path, first, "09:00:00"), save(tmp_path, second, "10:00:00", "before-write"),
             save(tmp_path, third, "11:00:00", "manual")]
    points = timeline.build(paths, [], current=third)
    assert [pt.path for pt in points] == list(reversed(paths))
    newest, middle, oldest = points
    assert newest.summary == "No changes since the previous backup" and newest.matches_mouse
    assert middle.reason == "Before a write" and middle.matches_mouse
    assert middle.summary == "Profile 3: Logo"
    assert oldest.first and not oldest.matches_mouse


def test_unreadable_backup_is_listed_not_fatal(tmp_path):
    bad = tmp_path / "g502-backup-20261030-080000-000000.json"
    bad.write_text("{}")
    points = timeline.build([bad, save(tmp_path, current(), "09:00:00")], [])
    assert points[1].problem and "Can't be read" in points[1].summary
