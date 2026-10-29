"""Profile data model: decode a profile sector to a JSON-friendly dict and back.

Layout (profile format 2, 256-byte sector), matching libratbag's
`union hidpp20_internal_profile`:

    0x00      report rate (1000 / Hz)
    0x01      default DPI index
    0x02      shift (sniper) DPI index
    0x03-0x0C 5 x DPI, little-endian, 0 = unused slot
    0x0D-0x0F profile colour        0x10 power mode     0x11 angle snapping
    0x12-0x1B reserved              0x1C-0x1D powersave timeout (BE)
    0x1E-0x1F poweroff timeout (BE)
    0x20-0x5F 16 x 4-byte button bindings
    0x60-0x9F 16 x 4-byte G-Shift bindings
    0xA0-0xCF name, UTF-16LE, 24 code units
    0xD0-0xE5 2 x 11-byte LED zones (0 = logo, 1 = DPI indicator lights)
    0xE6-0xFB 2 x 11-byte alternate LED zones (unused here)
    0xFC-0xFD free                  0xFE-0xFF CRC-16/CCITT (BE)

Every field decodes to something whose re-encoding gives back the exact bytes;
anything that would not (unknown binding type, odd padding) is kept as raw hex
instead, so parse -> serialise is always byte-identical.
"""

from __future__ import annotations

from .onboard import crc_ccitt

PROFILE_SIZE = 256
BINDING_SLOTS = 16
LED_SIZE = 11

# Slot names for the G502 HERO's 11 buttons, confirmed by pressing each one
# (2026-10-29, both layers): middle = wheel click, thumb_back/thumb_forward =
# rear/front thumb buttons, profile_switch = the button behind the wheel.
BUTTON_NAMES = [
    "left", "right", "middle", "thumb_back", "thumb_forward",
    "sniper", "dpi_down", "dpi_up", "profile_switch",
    "wheel_tilt_right", "wheel_tilt_left",
]

# LED zones in slot order, confirmed on the mouse (2026-10-29).
LED_ZONES = ["logo_led", "dpi_leds"]

# Special actions (binding type 0x90), libratbag hidpp20_profiles_specials.
SPECIALS = {
    0x01: "wheel_left", 0x02: "wheel_right",
    0x03: "dpi_up", 0x04: "dpi_down", 0x05: "dpi_cycle", 0x06: "dpi_default", 0x07: "dpi_shift",
    0x08: "profile_next", 0x09: "profile_prev", 0x0A: "profile_cycle",
    0x0B: "gshift", 0x0C: "battery_level",
}
SPECIAL_CODES = {v: k for k, v in SPECIALS.items()}

MODIFIERS = ["lctrl", "lshift", "lalt", "lgui", "rctrl", "rshift", "ralt", "rgui"]

# HID keyboard usage IDs (usage page 0x07) -> names.
KEYS: dict[int, str] = {0x04 + i: chr(ord("a") + i) for i in range(26)}
KEYS.update({0x1E + i: str((i + 1) % 10) for i in range(10)})
KEYS.update({
    0x28: "enter", 0x29: "escape", 0x2A: "backspace", 0x2B: "tab", 0x2C: "space",
    0x2D: "minus", 0x2E: "equal", 0x2F: "left_bracket", 0x30: "right_bracket",
    0x31: "backslash", 0x32: "non_us_hash", 0x33: "semicolon", 0x34: "apostrophe",
    0x35: "grave", 0x36: "comma", 0x37: "period", 0x38: "slash", 0x39: "caps_lock",
    0x46: "print_screen", 0x47: "scroll_lock", 0x48: "pause", 0x49: "insert",
    0x4A: "home", 0x4B: "page_up", 0x4C: "delete", 0x4D: "end", 0x4E: "page_down",
    0x4F: "right", 0x50: "left", 0x51: "down", 0x52: "up", 0x53: "num_lock",
    0x54: "kp_divide", 0x55: "kp_multiply", 0x56: "kp_minus", 0x57: "kp_plus",
    0x58: "kp_enter", 0x63: "kp_period", 0x64: "non_us_backslash", 0x65: "menu",
})
KEYS.update({0x3A + i: f"f{i + 1}" for i in range(12)})
KEYS.update({0x68 + i: f"f{i + 13}" for i in range(12)})
KEYS.update({0x59 + i: f"kp_{(i + 1) % 10}" for i in range(10)})
KEY_CODES = {v: k for k, v in KEYS.items()}

LED_EFFECTS = {0x00: "off", 0x01: "fixed", 0x03: "cycle", 0x0A: "breathing"}

REPORT_RATES = {125: 8, 250: 4, 500: 2, 1000: 1}


def _exact(decode, encode, raw: bytes, fallback):
    """decode(raw), but only if encode() reproduces raw exactly; else fallback(raw)."""
    try:
        value = decode(raw)
        if encode(value) == raw:
            return value
    except (KeyError, ValueError, UnicodeDecodeError, IndexError):
        pass
    return fallback(raw)


def _raw(data: bytes) -> dict:
    return {"type": "raw", "hex": data.hex()}


def _color(b: bytes) -> str:
    return "#" + b.hex().upper()


def _parse_color(s: str) -> bytes:
    s = s.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"colour {s!r} must be #RRGGBB")
    return bytes.fromhex(s)


# -- button bindings ---------------------------------------------------------

def _decode_binding(b: bytes) -> dict:
    if b == b"\xff" * 4:
        return {"type": "disabled"}
    if b[0] == 0x80 and b[1] == 0x01:
        mask = int.from_bytes(b[2:4], "big")
        return {"type": "mouse", "buttons": [i + 1 for i in range(16) if mask >> i & 1]}
    if b[0] == 0x80 and b[1] == 0x02:
        out = {"type": "key", "key": KEYS.get(b[3], f"0x{b[3]:02X}")}
        mods = [m for i, m in enumerate(MODIFIERS) if b[2] >> i & 1]
        if mods:
            out["modifiers"] = mods
        return out
    if b[0] == 0x80 and b[1] == 0x03:
        return {"type": "consumer", "usage": f"0x{int.from_bytes(b[2:4], 'big'):04X}"}
    if b[0] == 0x90 and b[1] in SPECIALS:
        out = {"type": "special", "action": SPECIALS[b[1]]}
        if b[2:4] != b"\x00\x00":
            out["arg"] = b[2:4].hex()
        return out
    if b[0] == 0x00 and b[2] == 0x00:
        return {"type": "macro", "sector": b[1], "offset": b[3]}
    raise ValueError("unknown binding")


def encode_binding(d: dict) -> bytes:
    t = d.get("type")
    if t == "disabled":
        return b"\xff" * 4
    if t == "mouse":
        mask = 0
        for n in d["buttons"]:
            if not 1 <= n <= 16:
                raise ValueError(f"mouse button {n} out of range 1-16")
            mask |= 1 << (n - 1)
        if not mask:
            raise ValueError("mouse binding needs at least one button")
        return bytes([0x80, 0x01]) + mask.to_bytes(2, "big")
    if t == "key":
        key = d["key"]
        code = KEY_CODES[key] if key in KEY_CODES else int(key, 0)
        mods = 0
        for m in d.get("modifiers", []):
            mods |= 1 << MODIFIERS.index(m)
        if not 0 < code <= 0xFF:
            raise ValueError(f"key code {code} out of range")
        return bytes([0x80, 0x02, mods, code])
    if t == "consumer":
        return bytes([0x80, 0x03]) + int(d["usage"], 0).to_bytes(2, "big")
    if t == "special":
        return bytes([0x90, SPECIAL_CODES[d["action"]]]) + bytes.fromhex(d.get("arg", "0000"))
    if t == "macro":
        return bytes([0x00, d["sector"], 0x00, d["offset"]])
    if t == "raw":
        return _hex(d["hex"], 4)
    raise ValueError(f"unknown binding type {t!r}")


def decode_binding(b: bytes) -> dict:
    return _exact(_decode_binding, encode_binding, b, _raw)


# -- LEDs ----------------------------------------------------------------------

def _decode_led(b: bytes) -> dict:
    effect = LED_EFFECTS.get(b[0])
    if effect == "off":
        return {"effect": "off"}
    if effect == "fixed":
        return {"effect": "fixed", "color": _color(b[1:4])}
    if effect == "cycle":
        return {"effect": "cycle", "period_ms": int.from_bytes(b[6:8], "big"), "brightness": b[8]}
    if effect == "breathing":
        return {"effect": "breathing", "color": _color(b[1:4]), "period_ms": int.from_bytes(b[4:6], "big"),
                "waveform": b[6], "brightness": b[7]}
    raise ValueError("unknown LED effect")


def encode_led(d: dict) -> bytes:
    e = d.get("effect")
    out = bytearray(LED_SIZE)
    if e == "off":
        pass
    elif e == "fixed":
        out[0] = 0x01
        out[1:4] = _parse_color(d["color"])
    elif e == "cycle":
        out[0] = 0x03
        out[6:8] = int(d["period_ms"]).to_bytes(2, "big")
        out[8] = _byte(d["brightness"], "brightness")
    elif e == "breathing":
        out[0] = 0x0A
        out[1:4] = _parse_color(d["color"])
        out[4:6] = int(d["period_ms"]).to_bytes(2, "big")
        out[6] = _byte(d.get("waveform", 0), "waveform")
        out[7] = _byte(d["brightness"], "brightness")
    elif e == "raw":
        return _hex(d["hex"], LED_SIZE)
    else:
        raise ValueError(f"unknown LED effect {e!r}")
    return bytes(out)


def decode_led(b: bytes) -> dict:
    return _exact(_decode_led, encode_led, b, lambda raw: {"effect": "raw", "hex": raw.hex()})


# -- helpers -------------------------------------------------------------------

def _byte(v, what: str) -> int:
    v = int(v)
    if not 0 <= v <= 0xFF:
        raise ValueError(f"{what} {v} out of range 0-255")
    return v


def _hex(s: str, length: int) -> bytes:
    b = bytes.fromhex(s)
    if len(b) != length:
        raise ValueError(f"expected {length} bytes of hex, got {len(b)}")
    return b


def _decode_name(b: bytes) -> str | None:
    if b == b"\xff" * len(b):
        return None  # factory profiles: no name
    text = b.decode("utf-16-le").split("\x00", 1)[0]
    return text


def _encode_name(name: str | None) -> bytes:
    if name is None:
        return b"\xff" * 48
    data = name.encode("utf-16-le")
    if len(data) > 48:
        raise ValueError(f"profile name {name!r} longer than 24 characters")
    return data.ljust(48, b"\x00")


def _decode_dpi(b: bytes) -> list[int]:
    slots = [int.from_bytes(b[i:i + 2], "little") for i in range(0, 10, 2)]
    levels = [v for v in slots if v]
    return levels


def _encode_dpi(levels: list[int]) -> bytes:
    if len(levels) > 5:
        raise ValueError("at most 5 DPI levels")
    for v in levels:
        if not 0 < v <= 0xFFFF:
            raise ValueError(f"DPI {v} out of range")
    return b"".join(int(v).to_bytes(2, "little") for v in levels).ljust(10, b"\x00")


# -- whole profile -------------------------------------------------------------

def decode_profile(data: bytes, button_count: int = len(BUTTON_NAMES)) -> dict:
    if len(data) != PROFILE_SIZE:
        raise ValueError(f"profile sector is {len(data)} bytes, expected {PROFILE_SIZE}")
    names = BUTTON_NAMES[:button_count] + [f"button_{i}" for i in range(len(BUTTON_NAMES), button_count)]

    def bindings(base: int) -> dict:
        return {names[i]: decode_binding(data[base + 4 * i:base + 4 * i + 4]) for i in range(button_count)}

    buttons = bindings(0x20)

    rate = data[0]
    profile: dict = {
        "name": _exact(_decode_name, _encode_name, data[0xA0:0xD0], lambda raw: {"raw": raw.hex()}),
        "report_rate_hz": 1000 // rate if rate and 1000 % rate == 0 and REPORT_RATES.get(1000 // rate) == rate
        else {"raw": rate},
        "dpi": {
            "levels": _exact(_decode_dpi, _encode_dpi, data[3:13], lambda raw: {"raw": raw.hex()}),
            "default_index": data[1],
            "shift_index": data[2],
        },
        "buttons": buttons,
        # Not stored on the mouse: the G-Shift layer is reachable only while a
        # main-layer button is bound to the gshift special.
        "gshift_layer": uses_gshift(buttons),
        "gshift_buttons": bindings(0x60),
        "lighting": {zone: decode_led(data[0xD0 + LED_SIZE * z:0xD0 + LED_SIZE * (z + 1)])
                     for z, zone in enumerate(LED_ZONES)},
    }
    advanced = {
        "profile_color": data[0x0D:0x10].hex(),
        "power_mode": data[0x10],
        "angle_snapping": data[0x11],
        "reserved": data[0x12:0x1C].hex(),
        "powersave_timeout": int.from_bytes(data[0x1C:0x1E], "big"),
        "poweroff_timeout": int.from_bytes(data[0x1E:0x20], "big"),
        "free": data[0xFC:0xFE].hex(),
    }
    # Unused binding slots and the alternate LED block are all FF on this mouse;
    # keep them only when they carry something.
    for key, start, end in (("unused_button_slots", 0x20 + 4 * button_count, 0x60),
                            ("unused_gshift_slots", 0x60 + 4 * button_count, 0xA0),
                            ("alt_lighting", 0xE6, 0xFC)):
        if data[start:end] != b"\xff" * (end - start):
            advanced[key] = data[start:end].hex()
    profile["advanced"] = advanced
    return profile


def uses_gshift(buttons: dict) -> bool:
    return any(b.get("type") == "special" and b.get("action") == "gshift" for b in buttons.values())


def encode_profile(p: dict, button_count: int = len(BUTTON_NAMES), with_crc: bool = True,
                   base: bytes | None = None) -> bytes:
    """Encode a profile dict. `gshift_layer: false` (single-layer mode) forbids a
    gshift binding on the main layer; `gshift_buttons` may then be left out, and
    the G-Shift table is copied unchanged from `base` (the sector on the mouse),
    so turning the layer back on later restores the old bindings."""
    names = BUTTON_NAMES[:button_count] + [f"button_{i}" for i in range(len(BUTTON_NAMES), button_count)]
    out = bytearray(b"\xff" * PROFILE_SIZE)
    adv = p.get("advanced", {})

    rate = p["report_rate_hz"]
    if isinstance(rate, dict):
        out[0] = _byte(rate["raw"], "report rate")
    elif rate in REPORT_RATES:
        out[0] = REPORT_RATES[rate]
    else:
        raise ValueError(f"report rate {rate} Hz not one of {sorted(REPORT_RATES)}")

    dpi = p["dpi"]
    levels = dpi["levels"]
    out[3:13] = _hex(levels["raw"], 10) if isinstance(levels, dict) else _encode_dpi(levels)
    count = 5 if isinstance(levels, dict) else len(levels)
    for key, off in (("default_index", 1), ("shift_index", 2)):
        idx = _byte(dpi[key], key)
        if idx >= max(count, 1):
            raise ValueError(f"dpi {key} {idx} points past the {count} DPI levels")
        out[off] = idx

    out[0x0D:0x10] = _hex(adv.get("profile_color", "ffffff"), 3)
    out[0x10] = _byte(adv.get("power_mode", 0xFF), "power_mode")
    out[0x11] = _byte(adv.get("angle_snapping", 0), "angle_snapping")
    out[0x12:0x1C] = _hex(adv.get("reserved", "ff" * 10), 10)
    out[0x1C:0x1E] = int(adv.get("powersave_timeout", 0xFFFF)).to_bytes(2, "big")
    out[0x1E:0x20] = int(adv.get("poweroff_timeout", 0xFFFF)).to_bytes(2, "big")

    layer = p.get("gshift_layer")
    if layer is not None:
        if not isinstance(layer, bool):
            raise ValueError(f"gshift_layer must be true or false, not {layer!r}")
        on = uses_gshift(p["buttons"])
        if layer and not on:
            raise ValueError("gshift_layer is true but no button is set to gshift, so the layer is unreachable")
        if not layer and on:
            raise ValueError("gshift_layer is false (single-layer mode) but a button is set to gshift")

    tables = [("buttons", 0x20, "unused_button_slots")]
    if "gshift_buttons" in p:
        tables.append(("gshift_buttons", 0x60, "unused_gshift_slots"))
    elif layer is False and base is not None:
        out[0x60:0xA0] = base[0x60:0xA0]
    else:
        raise ValueError("gshift_buttons is missing (it may only be left out with gshift_layer false)")

    for table, start, unused_key in tables:
        bindings = p[table]
        unknown = set(bindings) - set(names)
        if unknown:
            raise ValueError(f"{table}: unknown button names {sorted(unknown)}")
        for i, name in enumerate(names):
            if name not in bindings:
                raise ValueError(f"{table}: missing button {name!r}")
            out[start + 4 * i:start + 4 * i + 4] = encode_binding(bindings[name])
        tail = start + 4 * button_count
        if unused_key in adv:
            out[tail:start + 64] = _hex(adv[unused_key], start + 64 - tail)

    name = p["name"]
    out[0xA0:0xD0] = _hex(name["raw"], 48) if isinstance(name, dict) else _encode_name(name)

    unknown = set(p["lighting"]) - set(LED_ZONES)
    if unknown:
        raise ValueError(f"lighting: unknown zone names {sorted(unknown)} (expected {LED_ZONES})")
    for z, zone in enumerate(LED_ZONES):
        if zone not in p["lighting"]:
            raise ValueError(f"lighting: missing zone {zone!r}")
        out[0xD0 + LED_SIZE * z:0xD0 + LED_SIZE * (z + 1)] = encode_led(p["lighting"][zone])
    if "alt_lighting" in adv:
        out[0xE6:0xFC] = _hex(adv["alt_lighting"], 0xFC - 0xE6)
    out[0xFC:0xFE] = _hex(adv.get("free", "00ff"), 2)

    if with_crc:
        out[0xFE:0x100] = crc_ccitt(bytes(out[:0xFE])).to_bytes(2, "big")
    return bytes(out)


# -- export document -------------------------------------------------------------

EXPORT_FORMAT = "g502-onboard-profiles"
EXPORT_FORMAT_VERSION = 2   # 2: confirmed button/LED names, gshift_layer


def build_export(backup, include_rom: bool = False) -> dict:
    """Readable export of every profile listed in the directory of a Backup."""
    from datetime import datetime

    from . import __version__
    from .onboard import ROM_SECTOR_BASE, SECTOR_DIRECTORY, is_blank, parse_directory

    info = backup.meta["onboard_info"]
    buttons = info["button_count"]
    warnings = []
    profiles = []
    for entry in parse_directory(backup.sectors[SECTOR_DIRECTORY]):
        p = decode_profile(backup.sectors[entry.sector], buttons)
        profiles.append({"sector": entry.sector, "enabled": entry.enabled, **p})
        for table in ("buttons", "gshift_buttons"):
            dangling: dict[int, list[str]] = {}
            for name, b in p[table].items():
                if b["type"] == "macro":
                    target = backup.sectors.get(b["sector"])
                    if target is None or is_blank(target):
                        dangling.setdefault(b["sector"], []).append(name)
            for sector, names in dangling.items():
                effect = ("the G-Shift layer is off, so they are unreachable anyway"
                          if table == "gshift_buttons" and not p["gshift_layer"]
                          else "these buttons likely do nothing")
                warnings.append(f"profile in sector {entry.sector}: {table} {', '.join(names)} run macros in "
                                f"sector {sector}, which is empty; {effect}")
    doc = {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_FORMAT_VERSION,
        "tool_version": __version__,
        "exported": datetime.now().isoformat(timespec="seconds"),
        "source": str(backup.path) if backup.path else "mouse",
        "device": {
            "product_id": f"0x{backup.meta['product_id']:04X}",
            "firmware": backup.meta["firmware"][0]["version"] if backup.meta["firmware"] else None,
            "profile_format_id": info["profile_format_id"],
            "button_count": buttons,
            "sector_size": info["sector_size"],
        },
        "current_profile": backup.meta.get("current_profile"),
        "profiles": profiles,
    }
    if include_rom:
        doc["factory_profiles"] = [
            {"sector": s, **decode_profile(backup.sectors[s], buttons)}
            for s in backup.rom_sectors() if s != ROM_SECTOR_BASE
        ]
    if warnings:
        doc["warnings"] = warnings
    return doc
