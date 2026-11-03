import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import t3code_wal as wal


def palette(background, foreground, slots, color8="#555566"):
    colors = {f"color{i + 1}": slot for i, slot in enumerate(slots)}
    colors.update({f"color{i + 9}": slot for i, slot in enumerate(slots)})
    colors.update(
        {"color0": background, "color7": foreground, "color8": color8, "color15": foreground}
    )
    return {
        "special": {"background": background, "foreground": foreground, "cursor": foreground},
        "colors": colors,
    }


def hue_ramp(hue, chroma=0.15):
    return [wal.to_hex(wal.Oklch(0.4 + 0.05 * i, chroma, hue)) for i in range(6)]


# A real single-hue wallpaper: every slot is the same purple, and color8 is unreadable.
PURPLE = palette(
    "#0a0c22",
    "#c3c3c6",
    ["#5935b4", "#6439c4", "#6c40cb", "#7a4ed7", "#8d5ee5", "#9667ee"],
    color8="#3e3e8f",
)
CASES = {
    "purple": PURPLE,
    "gray": palette("#101010", "#d0d0d0", ["#444444", "#555555", "#666666", "#777777", "#888888", "#999999"]),
    "black": palette("#000000", "#ffffff", hue_ramp(250)),
    "dim foreground": palette("#1a1a2e", "#55556a", hue_ramp(300)),
    "low contrast palette": palette("#20242c", "#b0b4bc", ["#262a34", "#2a2e38", "#2c303c", "#303440", "#343844", "#383c48"]),
    "light": palette("#f2eee6", "#2b2622", hue_ramp(60)),
    "white": palette("#ffffff", "#000000", hue_ramp(260)),
}
CASES.update(
    {f"dark hue {hue}": palette(wal.to_hex(wal.Oklch(0.18, 0.03, hue)), "#d8d8d8", hue_ramp(hue)) for hue in range(0, 360, 20)}
)
CASES.update(
    {f"light hue {hue}": palette(wal.to_hex(wal.Oklch(0.94, 0.02, hue)), "#222222", hue_ramp(hue)) for hue in range(0, 360, 40)}
)

# Real `wal --saturate 0.3` output, including one `wal -l`.
with open(os.path.join(os.path.dirname(__file__), "palettes.json")) as file:
    CASES.update({f"real palette {i}": real for i, real in enumerate(json.load(file))})

# (foreground, surface, minimum contrast) that the T3 Code UI paints together.
PAIRS = [
    ("text", "canvas", 7),
    ("text", "surfaceOverlay", 7),
    ("textMuted", "canvas", 4.5),
    ("textMuted", "surfaceOverlay", 4.5),
    ("mutedForeground", "muted", 4.5),
    ("placeholder", "surfaceRaised", 4.5),
    ("secondaryForeground", "secondary", 4.5),
    ("accentForeground", "accent", 4.5),
    ("accentSurfaceForeground", "accentSurface", 4.5),
    ("messageForeground", "messageSurface", 4.5),
    ("messageActionForeground", "messageAction", 4.5),
    ("messageActionForeground", "messageActionHover", 4.5),
    ("codeForeground", "codeBackground", 4.5),
    ("errorForeground", "errorSurface", 4.5),
    ("warningForeground", "warningSurface", 4.5),
    ("updateForeground", "updateSurface", 4.5),
    ("searchMatchForeground", "searchMatchBackground", 4.5),
    ("searchMatchActiveForeground", "searchMatchActiveBackground", 4.5),
    ("sidebarForeground", "sidebar", 4.5),
    ("sidebarForeground", "sidebarRowSelected", 4.5),
    ("sidebarMutedForeground", "sidebar", 4.5),
    ("toolbarControlForeground", "toolbarControlHover", 4.5),
    ("terminalForeground", "terminalBackground", 7),
    ("accent", "canvas", 3),
    ("focus", "canvas", 3),
    ("error", "canvas", 3),
    ("warning", "canvas", 3),
    ("terminalCursor", "terminalBackground", 3),
]


class ThemeTest(unittest.TestCase):
    def check_every_case(self, check):
        for name, case in CASES.items():
            with self.subTest(name):
                check(wal.generate_theme(case)["colors"])

    def test_defines_every_role_as_opaque_hex(self):
        def check(colors):
            self.assertEqual(tuple(colors), wal.ROLES)
            for role, color in colors.items():
                self.assertRegex(color, r"^#[0-9a-f]{6}$", role)

        self.check_every_case(check)

    def test_every_painted_pair_is_readable(self):
        def check(colors):
            for foreground, surface, minimum in PAIRS:
                # On a mid-tone surface even pure white or black can fall short of 7:1.
                best = max(wal.contrast(edge, colors[surface]) for edge in ("#000000", "#ffffff"))
                ratio = wal.contrast(colors[foreground], colors[surface])
                self.assertGreaterEqual(ratio, min(minimum, best), f"{foreground} on {surface}")

        self.check_every_case(check)

    def test_mid_tone_canvas_stays_legible(self):
        # Rows lighter and darker than the crossover cannot both reach 4.5:1 with one color.
        colors = wal.generate_theme(palette("#5a5a70", "#e8e8e8", hue_ramp(200)))["colors"]
        for foreground, surface, minimum in PAIRS:
            ratio = wal.contrast(colors[foreground], colors[surface])
            self.assertGreaterEqual(ratio, min(minimum, 4), f"{foreground} on {surface}")

    def test_status_colors_keep_their_meaning_on_any_wallpaper(self):
        native = {name: wal.to_oklch(color).h for name, color in wal.NATIVE["dark"].items()}

        def check(colors):
            error = wal.to_oklch(colors["error"])
            warning = wal.to_oklch(colors["warning"])
            active = wal.to_oklch(colors["searchMatchActiveBackground"])
            # The hue shift plus what fitting a solved lightness into sRGB can add.
            self.assertLessEqual(wal.hue_distance(error.h, native["error"]), 14, "error stays red")
            self.assertLessEqual(wal.hue_distance(warning.h, native["warning"]), 14, "warning stays amber")
            self.assertLessEqual(
                wal.hue_distance(active.h, native["searchMatchActive"]), 14, "search stays amber"
            )
            self.assertGreaterEqual(wal.hue_distance(error.h, warning.h), 20)
            self.assertGreaterEqual(error.C, 0.1, "error stays colorful")
            self.assertGreaterEqual(warning.C, 0.1, "warning stays colorful")

        self.check_every_case(check)

    def test_status_colors_lean_toward_the_palette(self):
        colors = wal.generate_theme(PURPLE)["colors"]
        native = wal.to_oklch(wal.NATIVE["dark"]["error"]).h
        self.assertGreater(wal.hue_distance(wal.to_oklch(colors["error"]).h, native), 5)

    def test_elevation_ladder_is_ordered_from_the_canvas(self):
        ladder = ["canvas", "surface", "surfaceOverlay", "accentSurface", "border", "input"]

        def check(colors):
            distances = [
                abs(wal.to_oklch(colors[role]).L - wal.to_oklch(colors["canvas"]).L) for role in ladder
            ]
            self.assertEqual(distances, sorted(distances))
            self.assertEqual(len(set(colors[role] for role in ladder)), len(ladder))

        self.check_every_case(check)

    def test_row_states_stay_distinct(self):
        states = ["sidebar", "sidebarRowHover", "sidebarRowActive", "sidebarRowSelected"]

        def check(colors):
            self.assertEqual(len(set(colors[state] for state in states)), len(states))

        self.check_every_case(check)

    def test_palette_colors_survive_when_already_usable(self):
        theme = wal.generate_theme(PURPLE)
        colors = theme["colors"]
        self.assertEqual(theme["appearance"], "dark")
        self.assertEqual(theme["canvas"], "#0a0c22")
        self.assertEqual(colors["canvas"], "#0a0c22")
        self.assertEqual(colors["text"], "#c3c3c6")
        self.assertEqual(colors["accent"], "#8d5ee5")
        self.assertEqual(colors["messageAction"], "#8d5ee5")
        self.assertEqual(colors["terminalBackground"], "#0a0c22")
        self.assertEqual(colors["terminalCursor"], "#c3c3c6")

    def test_gray_wallpaper_gains_no_invented_tint(self):
        colors = wal.generate_theme(CASES["gray"])["colors"]
        for role in ("surface", "border", "input", "sidebarRowSelected"):
            self.assertLess(wal.to_oklch(colors[role]).C, 0.01, role)

    def test_accent_avoids_status_hues_when_the_palette_allows(self):
        red = hue_ramp(25)
        red[1] = wal.to_hex(wal.Oklch(0.6, 0.15, 150))
        colors = wal.generate_theme(palette("#120808", "#dddddd", red))["colors"]
        self.assertGreater(wal.hue_distance(wal.to_oklch(colors["accent"]).h, 25), 20)

    def test_accent_keeps_the_wallpaper_when_every_color_collides(self):
        theme = wal.generate_theme(palette("#120808", "#dddddd", hue_ramp(25)))
        self.assertLessEqual(wal.hue_distance(wal.to_oklch(theme["accent"]).h, 25), 5)

    def test_light_wallpaper_builds_downward(self):
        theme = wal.generate_theme(CASES["light"])
        self.assertEqual(theme["appearance"], "light")
        colors = theme["colors"]
        self.assertLess(wal.to_oklch(colors["border"]).L, wal.to_oklch(colors["canvas"]).L)

    def test_rejects_incomplete_palettes(self):
        for broken in (
            {},
            {"special": {"background": "#000000"}, "colors": {}},
            palette("#000", "#ffffff", hue_ramp(250)),
            palette("not a color", "#ffffff", hue_ramp(250)),
        ):
            with self.assertRaises(wal.PaletteError):
                wal.generate_theme(broken)


class PublishTest(unittest.TestCase):
    def test_publishes_one_regular_file_the_server_can_read(self):
        with tempfile.TemporaryDirectory() as directory:
            themes = os.path.join(directory, "userdata", "themes")
            wal.publish(wal.generate_theme(PURPLE), themes)
            wal.publish(wal.generate_theme(CASES["light"]), themes)
            self.assertEqual(os.listdir(themes), ["wal.json"])
            path = os.path.join(themes, "wal.json")
            info = os.lstat(path)
            self.assertTrue(stat.S_ISREG(info.st_mode))
            self.assertLessEqual(info.st_size, 32 * 1024)
            with open(path) as file:
                self.assertEqual(json.load(file)["appearance"], "light")

    def test_cli_reports_a_missing_palette(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = os.path.join(directory, "colors.json")
            self.assertEqual(wal.main(["--colors", missing, "--themes-dir", directory]), 1)
            self.assertEqual(os.listdir(directory), [])


if __name__ == "__main__":
    unittest.main()
