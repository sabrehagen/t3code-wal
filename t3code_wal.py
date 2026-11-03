#!/usr/bin/env python3
"""Publish a T3 Code theme generated from the current pywal colors."""

import argparse
import json
import math
import os
import re
import sys
import tempfile
from collections import namedtuple

THEME_ID = "wal"
THEME_NAME = "Wal"

# The roles in T3 Code's theme editor. T3 Code derives any role missing from this
# list from the canvas and accent seeds, so a newer T3 Code stays on-palette.
ROLES = (
    "canvas", "chrome", "toolbar", "toolbarForeground", "toolbarBorder", "toolbarControl",
    "toolbarControlForeground", "toolbarControlHover", "surface", "surfaceRaised",
    "surfaceOverlay", "text", "textMuted", "border", "input", "focus", "accent",
    "accentForeground", "secondary", "secondaryForeground", "muted", "mutedForeground",
    "placeholder", "secondaryLabel", "iconMuted", "error", "errorForeground", "errorSurface",
    "warning", "warningForeground", "warningSurface", "update", "updateForeground",
    "updateSurface", "accentSurface", "accentSurfaceForeground", "messageSurface",
    "messageForeground", "messageAction", "messageActionForeground", "messageActionHover",
    "codeBackground", "codeForeground", "searchMatchBackground", "searchMatchForeground",
    "searchMatchActiveBackground", "searchMatchActiveForeground", "sidebar", "sidebarForeground",
    "sidebarMutedForeground", "sidebarControlSurface", "sidebarRowHover", "sidebarRowActive",
    "sidebarRowSelected", "sidebarBorder", "terminalBackground", "terminalForeground",
    "terminalCursor", "terminalSelection", "terminalScrollbar", "terminalScrollbarHover",
)

# T3 Code's own dividing line between dark and light canvases.
DARK_LUMINANCE = 0.179

# One unit is roughly one step of vscode-wal's shadeColor (an RGB offset) on a dark
# background, so the ladder below reads in the same numbers, but stays perceptually even.
LADDER_UNIT = 0.0043

# T3 Code's native status colors. These carry meaning a wallpaper cannot supply: pywal
# slots are sorted clusters, so color1 is not red and may be the same purple as color5.
NATIVE = {
    "dark": {
        "error": "#fb414a", "errorForeground": "#ff6467",
        "warning": "#fe9a00", "warningForeground": "#ffb900",
        "searchMatch": "#8c6c1f", "searchMatchActive": "#eea52b",
    },
    "light": {
        "error": "#fb2c36", "errorForeground": "#c10007",
        "warning": "#fe9a00", "warningForeground": "#bb4d00",
        "searchMatch": "#ffde8b", "searchMatchActive": "#eea52b",
    },
}
STATUS_SURFACE_MIX = {"dark": 0.16, "light": 0.08}
MUTED_CONTRAST = {"dark": 5.082, "light": 4.705}

# Small enough that red stays red and amber stays amber, on any wallpaper hue.
MAX_HUE_SHIFT = 10
MIN_ACCENT_CHROMA = 0.04
# An accent this close to a status hue would make primary buttons read as an alarm.
MIN_STATUS_HUE_DISTANCE = 20

Oklch = namedtuple("Oklch", "L C h")


class PaletteError(Exception):
    pass


def hex_to_rgb(color):
    return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{round(min(255, max(0, channel))):02x}" for channel in rgb)


def _to_linear(channel):
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(channel):
    c = min(1, max(0, channel))
    return 255 * (c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)


def to_oklch(color):
    r, g, b = (_to_linear(channel) for channel in hex_to_rgb(color))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
    a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
    b_ = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
    return Oklch(L, math.hypot(a, b_), math.degrees(math.atan2(b_, a)) % 360)


def _oklch_to_linear(color):
    radians = math.radians(color.h)
    a, b = color.C * math.cos(radians), color.C * math.sin(radians)
    l = (color.L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (color.L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (color.L - 0.0894841775 * a - 1.291485548 * b) ** 3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
    )


def to_hex(color):
    """Reduces chroma, never lightness or hue, until the color fits in sRGB."""
    color = Oklch(min(1, max(0, color.L)), color.C, color.h)
    in_gamut = lambda C: all(
        -0.0001 <= c <= 1.0001 for c in _oklch_to_linear(color._replace(C=C))
    )
    if not in_gamut(color.C):
        low, high = 0, color.C
        for _ in range(20):
            mid = (low + high) / 2
            low, high = (mid, high) if in_gamut(mid) else (low, mid)
        color = color._replace(C=low)
    return rgb_to_hex(_to_srgb(channel) for channel in _oklch_to_linear(color))


def luminance(color):
    r, g, b = (_to_linear(channel) for channel in hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def mix(base, overlay, amount):
    return rgb_to_hex(
        a + (b - a) * amount for a, b in zip(hex_to_rgb(base), hex_to_rgb(overlay))
    )


def hue_distance(first, second):
    return abs((first - second + 180) % 360 - 180)


def _solve_towards(color, surfaces, minimum, target_L):
    """Bisects lightness, measuring the 8-bit color that will actually be painted."""
    source = to_oklch(color)
    worst = lambda value: min(contrast(value, surface) for surface in surfaces)
    best = None
    near, far = source.L, target_L
    for _ in range(24):
        mid = (near + far) / 2
        candidate = to_hex(source._replace(L=mid))
        if worst(candidate) >= minimum:
            best, far = candidate, mid
        else:
            near = mid
    if best is None:
        edge = to_hex(source._replace(L=target_L))
        return edge if worst(edge) >= minimum else None
    return best


def readable(color, surfaces, minimum):
    """Moves only lightness, so a color too dim on a surface keeps its hue."""
    if min(contrast(color, surface) for surface in surfaces) >= minimum:
        return color
    # Moving away from the surfaces is what normally helps. Mid-tone surfaces can
    # require the other direction, and only black or white can meet some targets.
    surface_is_dark = luminance(surfaces[0]) < DARK_LUMINANCE
    for target_L in (1, 0) if surface_is_dark else (0, 1):
        solved = _solve_towards(color, surfaces, minimum, target_L)
        if solved is not None:
            return solved
    return max(
        ("#000000", "#ffffff"),
        key=lambda edge: min(contrast(edge, surface) for surface in surfaces),
    )


def soften(foreground, toward, requirements):
    """The furthest mix toward a surface that still meets every (surface, ratio) pair."""
    meets = lambda value: all(contrast(value, surface) >= ratio for surface, ratio in requirements)
    best = foreground
    low, high = 0, 1
    for _ in range(16):
        mid = (low + high) / 2
        candidate = mix(foreground, toward, mid)
        if meets(candidate):
            best, low = candidate, mid
        else:
            high = mid
    return best


def foreground_on(surfaces, preferences, minimum=4.5):
    """The first preferred color that already reads, else the closest one made readable."""
    surfaces = surfaces if isinstance(surfaces, (list, tuple)) else [surfaces]
    worst = lambda value: min(contrast(value, surface) for surface in surfaces)
    for preference in preferences:
        if worst(preference) >= minimum:
            return preference
    return readable(max(preferences, key=worst), surfaces, minimum)


def choose_accent(slots):
    """color5 is the accent, as in vscode-wal, unless it is gray or collides with a status hue."""
    candidates = [slots[index] for index in (5, 4, 6, 3, 2, 1)]
    chromatic = [c for c in candidates if to_oklch(c).C >= MIN_ACCENT_CHROMA]
    status_hues = [to_oklch(NATIVE["dark"][name]).h for name in ("error", "warning")]
    for candidate in chromatic:
        hue = to_oklch(candidate).h
        if all(hue_distance(hue, status) >= MIN_STATUS_HUE_DISTANCE for status in status_hues):
            return candidate
    return chromatic[0] if chromatic else slots[5]


def harmonize(color, accent, chroma_scale):
    """Leans a semantic color toward the palette without changing what it means."""
    source = to_oklch(color)
    target = to_oklch(accent)
    hue = source.h
    if target.C >= MIN_ACCENT_CHROMA:
        delta = (target.h - source.h + 180) % 360 - 180
        hue += math.copysign(min(abs(delta) / 2, MAX_HUE_SHIFT), delta)
    return to_hex(Oklch(source.L, source.C * chroma_scale, hue % 360))


def generate_colors(background, foreground, cursor, slots):
    """Maps a pywal palette onto T3 Code's roles. All colors are #rrggbb."""
    appearance = "dark" if luminance(background) < DARK_LUMINANCE else "light"
    direction = 1 if appearance == "dark" else -1
    native = NATIVE[appearance]

    canvas = to_oklch(background)
    raw_accent = choose_accent(slots)
    accent_lch = to_oklch(raw_accent)
    palette_chroma = max(to_oklch(slots[index]).C for index in range(1, 7))

    # A gray wallpaper stays gray: the tint comes only from color the palette has.
    # The same chroma that is subtle on a dark surface is loud on a light one.
    tint_limit = 0.045 if appearance == "dark" else 0.02
    tint_chroma = max(min(canvas.C, 0.06), min(tint_limit, accent_lch.C * 0.22))
    neutral_hue = canvas.h if canvas.C >= 0.01 else accent_lch.h

    def rise(units, chroma=None, hue=None):
        """A step away from the canvas. vscode-wal's ladder: menus 10, hover 16, border 28."""
        return to_hex(
            Oklch(
                min(0.98, max(0, canvas.L + direction * units * LADDER_UNIT)),
                tint_chroma if chroma is None else chroma,
                neutral_hue if hue is None else hue,
            )
        )

    def tinted(units, strength=0.5):
        """A step that also says "selected" or "yours", so it carries the accent's hue."""
        return rise(units, max(tint_chroma, min(0.11, accent_lch.C * strength)), accent_lch.h)

    surface = rise(6)
    surface_raised = rise(8)
    surface_overlay = rise(10)
    secondary = rise(12)
    muted = rise(8)
    accent_surface = rise(20)
    message_surface = tinted(22)
    # T3 Code's sidebar recedes behind the canvas in both of its native palettes.
    sidebar = to_hex(canvas._replace(L=max(0, canvas.L - 0.02)))
    row_hover, row_active, row_selected = tinted(14), tinted(20), tinted(26)
    update_surface = mix(background, raw_accent, STATUS_SURFACE_MIX[appearance])

    text = readable(foreground, [background, surface_overlay], 7)
    on = lambda *surfaces: readable(text, list(surfaces), 4.6)

    muted_text = soften(
        text,
        background,
        [(background, MUTED_CONTRAST[appearance]), (surface_overlay, 4.6)],
    )

    accent = readable(raw_accent, [background, surface_raised], 3)
    focus_source = slots[12] if to_oklch(slots[12]).C >= MIN_ACCENT_CHROMA else accent
    focus = readable(focus_source, [background, surface_raised], 3)
    action_foreground = foreground_on(accent, [background, text])
    # vscode-wal's button.hoverBackground is color5 shaded by +12, always lighter. Moving
    # away from the label instead keeps one label readable on both button states.
    away_from_label = 1 if luminance(accent) >= luminance(action_foreground) else -1
    accent_hover = to_hex(
        to_oklch(accent)._replace(L=to_oklch(accent).L + away_from_label * 12 * LADDER_UNIT)
    )

    chroma_scale = min(1, max(0.7, palette_chroma / 0.15))
    semantic = lambda name: harmonize(native[name], raw_accent, chroma_scale)

    def status(name):
        fill = readable(semantic(name), [background], 3)
        tint = mix(background, fill, STATUS_SURFACE_MIX[appearance])
        return fill, readable(semantic(name + "Foreground"), [tint], 4.6), tint

    error, error_foreground, error_surface = status("error")
    warning, warning_foreground, warning_surface = status("warning")
    search_match = semantic("searchMatch")
    search_active = semantic("searchMatchActive")

    colors = {
        "canvas": background,
        "chrome": background,
        "toolbar": background,
        "toolbarForeground": text,
        "toolbarBorder": rise(28),
        "toolbarControl": rise(10),
        "toolbarControlForeground": on(rise(10), rise(16)),
        "toolbarControlHover": rise(16),
        "surface": surface,
        "surfaceRaised": surface_raised,
        "surfaceOverlay": surface_overlay,
        "text": text,
        "textMuted": muted_text,
        "border": rise(28),
        "input": rise(34),
        "focus": focus,
        "accent": accent,
        "accentForeground": foreground_on(accent, [background, text]),
        "secondary": secondary,
        "secondaryForeground": on(secondary),
        "muted": muted,
        "mutedForeground": soften(text, muted, [(muted, 4.6), (surface_overlay, 4.6)]),
        "placeholder": soften(text, surface_raised, [(surface_raised, 4.6)]),
        "secondaryLabel": muted_text,
        "iconMuted": muted_text,
        "error": error,
        "errorForeground": error_foreground,
        "errorSurface": error_surface,
        "warning": warning,
        "warningForeground": warning_foreground,
        "warningSurface": warning_surface,
        "update": accent,
        "updateForeground": readable(accent, [update_surface], 4.6),
        "updateSurface": update_surface,
        "accentSurface": accent_surface,
        "accentSurfaceForeground": on(accent_surface),
        "messageSurface": message_surface,
        "messageForeground": on(message_surface),
        "messageAction": accent,
        "messageActionForeground": action_foreground,
        "messageActionHover": accent_hover,
        "codeBackground": surface,
        "codeForeground": on(surface),
        "searchMatchBackground": search_match,
        "searchMatchForeground": foreground_on(search_match, [text, background]),
        "searchMatchActiveBackground": search_active,
        "searchMatchActiveForeground": foreground_on(search_active, [background, text]),
        "sidebar": sidebar,
        "sidebarForeground": on(sidebar, row_selected),
        "sidebarMutedForeground": soften(text, sidebar, [(sidebar, 5.5), (row_selected, 4.6)]),
        "sidebarControlSurface": rise(6),
        "sidebarRowHover": row_hover,
        "sidebarRowActive": row_active,
        "sidebarRowSelected": row_selected,
        "sidebarBorder": rise(24),
        "terminalBackground": background,
        "terminalForeground": readable(foreground, [background], 7),
        "terminalCursor": readable(cursor, [background], 3),
        "terminalSelection": tinted(40),
        "terminalScrollbar": rise(24),
        "terminalScrollbarHover": rise(36),
    }
    return appearance, raw_accent, {role: colors[role] for role in ROLES}


def generate_theme(wal):
    """Builds a T3 Code environment theme from pywal's parsed colors.json."""
    try:
        background = wal["special"]["background"]
        foreground = wal["special"]["foreground"]
        cursor = wal["special"].get("cursor", foreground)
        slots = [wal["colors"][f"color{index}"] for index in range(16)]
    except (KeyError, TypeError, AttributeError) as error:
        raise PaletteError(f"missing pywal color: {error}") from error
    palette = [background, foreground, cursor, *slots]
    invalid = [c for c in palette if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(c))]
    if invalid:
        raise PaletteError(f"not a #rrggbb color: {invalid[0]}")

    background, foreground, cursor, *slots = (color.lower() for color in palette)
    appearance, accent, colors = generate_colors(background, foreground, cursor, slots)
    return {
        "version": 1,
        "name": THEME_NAME,
        "appearance": appearance,
        "canvas": background,
        "accent": accent,
        "colors": colors,
    }


def default_colors_path():
    if os.environ.get("PYWAL_CACHE_DIR"):
        return os.path.join(os.environ["PYWAL_CACHE_DIR"], "colors.json")
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "wal", "colors.json")


def default_themes_dir():
    home = os.environ.get("T3CODE_HOME") or os.path.expanduser("~/.t3")
    return os.path.join(home, "userdata", "themes")


def publish(theme, themes_dir):
    """T3 Code watches this directory and repaints when wal.json is renamed into place."""
    os.makedirs(themes_dir, exist_ok=True)
    destination = os.path.join(themes_dir, f"{THEME_ID}.json")
    # The server ignores non-.json names, and refuses symlinks, so this must be a real file.
    descriptor, temporary = tempfile.mkstemp(prefix=f".{THEME_ID}.", suffix=".tmp", dir=themes_dir)
    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump(theme, file, indent=2)
            file.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, destination)
    except BaseException:
        os.unlink(temporary)
        raise
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(prog="t3code-wal", description=__doc__)
    parser.add_argument(
        "--colors",
        default=default_colors_path(),
        help="pywal colors.json (default: %(default)s)",
    )
    parser.add_argument(
        "--themes-dir",
        default=default_themes_dir(),
        help="T3 Code themes directory (default: %(default)s)",
    )
    parser.add_argument(
        "--stdout", action="store_true", help="print the theme instead of publishing it"
    )
    args = parser.parse_args(argv)

    try:
        with open(args.colors) as file:
            theme = generate_theme(json.load(file))
    except OSError as error:
        print(f"t3code-wal: cannot read {args.colors}: {error.strerror}. Run wal first.", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"t3code-wal: {args.colors} is not valid JSON: {error}", file=sys.stderr)
        return 1
    except PaletteError as error:
        print(f"t3code-wal: {args.colors}: {error}", file=sys.stderr)
        return 1

    if args.stdout:
        print(json.dumps(theme, indent=2))
        return 0
    try:
        print(publish(theme, args.themes_dir))
    except OSError as error:
        print(f"t3code-wal: cannot write to {args.themes_dir}: {error.strerror}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
