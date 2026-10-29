import pytest

from g502 import backup
from g502.backup import Backup

from .test_onboard import load_sectors

INFO = {"sector_count": 16, "sector_size": 256}


def make(sectors) -> Backup:
    return Backup({"product_id": 0xC08B, "firmware": [], "onboard_info": INFO}, dict(sectors))


def test_fixture_backup_is_valid():
    assert backup.check_backup(make(load_sectors())) == []


def test_plan_writes_only_changed_sectors_and_directory_last():
    cur = load_sectors()
    new = dict(cur)
    new[0x0000] = cur[0x0000][:-1] + b"\x00"
    new[0x0004] = cur[0x0003]
    new[0x0002] = cur[0x0005]
    assert backup.plan_restore(make(new), make(cur)).write == [0x0002, 0x0004, 0x0000]


def test_plan_explicit_sectors_and_rom_refused():
    cur = make(load_sectors())
    assert backup.plan_restore(cur, cur).write == []
    assert backup.plan_restore(cur, cur, [0, 3]).write == [3, 0]
    with pytest.raises(ValueError):
        backup.plan_restore(cur, cur, [0x0101])


def test_bad_crc_and_dangling_directory_rejected():
    s = load_sectors()
    s[0x0003] = s[0x0003][:-1] + bytes([s[0x0003][-1] ^ 1])
    problems = backup.check_backup(make(s))
    assert any("0x0003 has a bad CRC" in p for p in problems)
    assert any("points at sector 0x0003" in p for p in problems)


def test_save_load_roundtrip(tmp_path):
    b = make(load_sectors())
    b.meta.update(backup_format=1, created="2026-10-29T10:00:00.000001")
    path = backup.save_backup(b, tmp_path)
    loaded = backup.load_backup(path)
    assert loaded.sectors == b.sectors and backup.compare_backups(b, loaded) == []


def test_blank_sectors_never_written():
    cur = load_sectors()
    plan = backup.plan_restore(make(cur), make(cur), [3, 6, 7])
    assert plan.write == [3] and set(plan.skipped) == {6, 7}
    # backup blank where the mouse has data: still skipped (cannot return to blank)
    mouse = dict(cur)
    mouse[6] = cur[3]
    plan = backup.plan_restore(make(cur), make(mouse))
    assert plan.write == [] and "blank in backup" in plan.skipped[6]


def test_filling_empty_sector_needs_flag():
    cur = load_sectors()
    new = dict(cur)
    new[6] = cur[3]
    plan = backup.plan_restore(make(new), make(cur))
    assert plan.write == [] and "blank on the mouse" in plan.skipped[6]
    assert backup.plan_restore(make(new), make(cur), allow_fill_empty=True).write == [6]
