"""Human-readable labels for profile settings, used by the GUI and its change lists."""

from __future__ import annotations

from . import model

BUTTON_LABELS = {
    "left": "Left click",
    "right": "Right click",
    "middle": "Wheel click",
    "thumb_back": "Thumb back",
    "thumb_forward": "Thumb forward",
    "sniper": "Sniper button",
    "dpi_down": "DPI down button",
    "dpi_up": "DPI up button",
    "profile_switch": "Profile button (behind wheel)",
    "wheel_tilt_right": "Wheel tilt right",
    "wheel_tilt_left": "Wheel tilt left",
}

ZONE_LABELS = {"logo_led": "Logo", "dpi_leds": "DPI indicator lights"}

MOUSE_BUTTONS = {1: "Left click", 2: "Right click", 3: "Middle click", 4: "Back", 5: "Forward"}

SPECIAL_LABELS = {
    "wheel_left": "Scroll left",
    "wheel_right": "Scroll right",
    "dpi_up": "DPI up",
    "dpi_down": "DPI down",
    "dpi_cycle": "DPI cycle",
    "dpi_default": "DPI default",
    "dpi_shift": "DPI shift (sniper)",
    "profile_next": "Next profile",
    "profile_prev": "Previous profile",
    "profile_cycle": "Cycle profiles",
    "gshift": "G-Shift",
    "battery_level": "Battery level",
}

MODIFIER_LABELS = {
    "lctrl": "Ctrl", "lshift": "Shift", "lalt": "Alt", "lgui": "Win",
    "rctrl": "Right Ctrl", "rshift": "Right Shift", "ralt": "Right Alt", "rgui": "Right Win",
}

# Consumer-page usages (media keys) most people want.
CONSUMER_LABELS = {
    "0x00E9": "Volume up", "0x00EA": "Volume down", "0x00E2": "Mute",
    "0x00CD": "Play / pause", "0x00B5": "Next track", "0x00B6": "Previous track", "0x00B7": "Stop",
    "0x0192": "Calculator", "0x0194": "File explorer", "0x018A": "Mail", "0x0223": "Browser home",
}

_KEY_SPECIAL = {
    "enter": "Enter", "escape": "Esc", "backspace": "Backspace", "tab": "Tab", "space": "Space",
    "minus": "-", "equal": "=", "left_bracket": "[", "right_bracket": "]", "backslash": "\\",
    "non_us_hash": "# (non-US)", "semicolon": ";", "apostrophe": "'", "grave": "`", "comma": ",",
    "period": ".", "slash": "/", "caps_lock": "Caps Lock", "print_screen": "Print Screen",
    "scroll_lock": "Scroll Lock", "pause": "Pause", "insert": "Insert", "home": "Home",
    "page_up": "Page Up", "delete": "Delete", "end": "End", "page_down": "Page Down",
    "right": "Right arrow", "left": "Left arrow", "down": "Down arrow", "up": "Up arrow",
    "num_lock": "Num Lock", "kp_divide": "Numpad /", "kp_multiply": "Numpad *", "kp_minus": "Numpad -",
    "kp_plus": "Numpad +", "kp_enter": "Numpad Enter", "kp_period": "Numpad .",
    "non_us_backslash": "\\ (non-US)", "menu": "Menu",
}


def key_label(name: str) -> str:
    if name in _KEY_SPECIAL:
        return _KEY_SPECIAL[name]
    if len(name) == 1:
        return name.upper()
    if name.startswith("kp_"):
        return "Numpad " + name[3:]
    if name[0] == "f" and name[1:].isdigit():
        return name.upper()
    return name


def key_names_sorted() -> list[str]:
    """Key names in a sensible order for a picker: letters, digits, F-keys, the rest."""
    names = list(model.KEY_CODES)

    def order(n: str):
        if len(n) == 1 and n.isalpha():
            return (0, n)
        if len(n) == 1:
            return (1, n)
        if n[0] == "f" and n[1:].isdigit():
            return (2, int(n[1:]))
        if n.startswith("kp_"):
            return (4, n)
        return (3, key_label(n))
    return sorted(names, key=order)


def describe_binding(b: dict) -> str:
    t = b.get("type")
    if t == "disabled":
        return "Disabled"
    if t == "mouse":
        return " + ".join(MOUSE_BUTTONS.get(n, f"Mouse button {n}") for n in b["buttons"])
    if t == "key":
        return "+".join([MODIFIER_LABELS[m] for m in b.get("modifiers", [])] + [key_label(b["key"])])
    if t == "consumer":
        return CONSUMER_LABELS.get(b["usage"], f"Media key {b['usage']}")
    if t == "special":
        return SPECIAL_LABELS.get(b["action"], b["action"])
    if t == "macro":
        return f"Macro (stored in sector {b['sector']})"
    return f"Unrecognised ({b.get('hex', '?')}), kept as is"


def describe_led(z: dict) -> str:
    e = z.get("effect")
    if e == "off":
        return "Off"
    if e == "fixed":
        return f"Solid {z['color']}"
    if e == "cycle":
        return f"Colour cycle, {z['period_ms'] / 1000:g} s, brightness {z['brightness']}%"
    if e == "breathing":
        return f"Breathing {z['color']}, {z['period_ms'] / 1000:g} s, brightness {z['brightness']}%"
    return f"Unrecognised ({z.get('hex', '?')}), kept as is"


def _dpi_value(profile: dict, index: int):
    levels = profile["dpi"]["levels"]
    return levels[index] if isinstance(levels, list) and index < len(levels) else f"level {index + 1}"


def describe_changes(old: dict, new: dict) -> list[tuple[str, str, str, str]]:
    """(area, setting, before, after) rows for everything that differs between two profiles."""
    rows = []

    def add(area, setting, a, b):
        if a != b:
            rows.append((area, setting, a, b))

    add("Profile", "Name", str(old.get("name")), str(new.get("name")))
    if "enabled" in old or "enabled" in new:
        add("Profile", "Status", "Active" if old.get("enabled") else "Deactivated",
            "Active" if new.get("enabled") else "Deactivated")
    add("Profile", "Polling rate", f"{old['report_rate_hz']} Hz", f"{new['report_rate_hz']} Hz")
    add("DPI", "Levels", ", ".join(map(str, old["dpi"]["levels"])), ", ".join(map(str, new["dpi"]["levels"])))
    add("DPI", "Default", str(_dpi_value(old, old["dpi"]["default_index"])),
        str(_dpi_value(new, new["dpi"]["default_index"])))
    add("DPI", "Sniper (DPI shift)", str(_dpi_value(old, old["dpi"]["shift_index"])),
        str(_dpi_value(new, new["dpi"]["shift_index"])))
    add("Buttons", "G-Shift layer", "On" if old.get("gshift_layer") else "Off",
        "On" if new.get("gshift_layer") else "Off")
    for table, area in (("buttons", "Buttons"), ("gshift_buttons", "G-Shift layer")):
        a, b = old.get(table, {}), new.get(table)
        if b is None:      # left out: kept from the mouse
            continue
        for name in b:
            add(area, BUTTON_LABELS.get(name, name), describe_binding(a.get(name, {})), describe_binding(b[name]))
    for zone, label in ZONE_LABELS.items():
        add("Lighting", label, describe_led(old["lighting"][zone]), describe_led(new["lighting"][zone]))
    for k in sorted(set(old.get("advanced", {})) | set(new.get("advanced", {}))):
        add("Advanced", k, str(old.get("advanced", {}).get(k)), str(new.get("advanced", {}).get(k)))
    return rows
