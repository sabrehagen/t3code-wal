# Checks the guarantees of one generated theme, independently of how t3code-wal computes it.
# Input: "appearance dark", "seed #rrggbb", then one "role #rrggbb" per color. Set -v name=CASE.

function min(a, b) { return a < b ? a : b }
function max(a, b) { return a > b ? a : b }
function abs(x) { return x < 0 ? -x : x }
function wrap_hue(x) { x = x % 360; return x < 0 ? x + 360 : x }
function hue_distance(a, b) { return abs(wrap_hue(a - b + 180) - 180) }

function fail(message) {
    printf "FAIL %s: %s\n", name, message
    failed = 1
}

function channel(color, i) {
    return (index(HEX, substr(color, 2 * i, 1)) - 1) * 16 + index(HEX, substr(color, 2 * i + 1, 1)) - 1
}

function to_linear(value) {
    value /= 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ^ 2.4
}

function contrast(first, second,   a, b) {
    a = 0.2126 * to_linear(channel(first, 1)) + 0.7152 * to_linear(channel(first, 2)) + 0.0722 * to_linear(channel(first, 3))
    b = 0.2126 * to_linear(channel(second, 1)) + 0.7152 * to_linear(channel(second, 2)) + 0.0722 * to_linear(channel(second, 3))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)
}

function parse(color,   r, g, b, l, m, s, A, B) {
    r = to_linear(channel(color, 1)); g = to_linear(channel(color, 2)); b = to_linear(channel(color, 3))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ^ (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ^ (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ^ (1 / 3)
    ok_L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
    A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
    B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
    ok_C = sqrt(A * A + B * B)
    ok_h = wrap_hue(atan2(B, A) * (180 / atan2(0, -1)))
}
function lightness_of(color) { parse(color); return ok_L }
function chroma_of(color) { parse(color); return ok_C }
function hue_of(color) { parse(color); return ok_h }

# Rows lighter and darker than the crossover of a mid-tone canvas cannot both reach 4.5:1
# with one color, and on a mid-tone surface even pure white or black can miss 7:1.
function readable(foreground, surface, minimum,   best, floor, ratio) {
    best = max(contrast("#000000", c[surface]), contrast("#ffffff", c[surface]))
    floor = name == "mid-tone" ? min(minimum, 4) : min(minimum, best)
    ratio = contrast(c[foreground], c[surface])
    if (ratio < floor) fail(foreground " on " surface " is " ratio ":1, needs " floor)
}

function all_distinct(roles,   list, n, i, seen) {
    n = split(roles, list, " ")
    for (i = 1; i <= n; i++) {
        if (c[list[i]] in seen) fail(list[i] " repeats another color in: " roles)
        seen[c[list[i]]] = 1
    }
}

BEGIN { HEX = "0123456789abcdef" }
$1 == "appearance" { appearance = $2; next }
$1 == "seed" { seed = $2; next }
{ c[$1] = $2; count++ }

END {
    roles = "canvas chrome toolbar toolbarForeground toolbarBorder toolbarControl toolbarControlForeground"
    roles = roles " toolbarControlHover surface surfaceRaised surfaceOverlay text textMuted border input focus"
    roles = roles " accent accentForeground secondary secondaryForeground muted mutedForeground placeholder"
    roles = roles " secondaryLabel iconMuted error errorForeground errorSurface warning warningForeground"
    roles = roles " warningSurface update updateForeground updateSurface accentSurface accentSurfaceForeground"
    roles = roles " messageSurface messageForeground messageAction messageActionForeground messageActionHover"
    roles = roles " codeBackground codeForeground searchMatchBackground searchMatchForeground"
    roles = roles " searchMatchActiveBackground searchMatchActiveForeground sidebar sidebarForeground"
    roles = roles " sidebarMutedForeground sidebarControlSurface sidebarRowHover sidebarRowActive"
    roles = roles " sidebarRowSelected sidebarBorder terminalBackground terminalForeground terminalCursor"
    roles = roles " terminalSelection terminalScrollbar terminalScrollbarHover"
    expected = split(roles, list, " ")
    if (count != expected) fail("has " count " roles, expected " expected)
    for (i = 1; i <= expected; i++)
        if (c[list[i]] !~ /^#[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]$/) fail(list[i] " is not #rrggbb: " c[list[i]])
    if (failed) exit 1

    # What the T3 Code UI paints together.
    readable("text", "canvas", 7)
    readable("text", "surfaceOverlay", 7)
    readable("textMuted", "canvas", 4.5)
    readable("textMuted", "surfaceOverlay", 4.5)
    readable("mutedForeground", "muted", 4.5)
    readable("placeholder", "surfaceRaised", 4.5)
    readable("secondaryForeground", "secondary", 4.5)
    readable("accentForeground", "accent", 4.5)
    readable("accentSurfaceForeground", "accentSurface", 4.5)
    readable("messageForeground", "messageSurface", 4.5)
    readable("messageActionForeground", "messageAction", 4.5)
    readable("messageActionForeground", "messageActionHover", 4.5)
    readable("codeForeground", "codeBackground", 4.5)
    readable("errorForeground", "errorSurface", 4.5)
    readable("warningForeground", "warningSurface", 4.5)
    readable("updateForeground", "updateSurface", 4.5)
    readable("searchMatchForeground", "searchMatchBackground", 4.5)
    readable("searchMatchActiveForeground", "searchMatchActiveBackground", 4.5)
    readable("sidebarForeground", "sidebar", 4.5)
    readable("sidebarForeground", "sidebarRowSelected", 4.5)
    readable("sidebarMutedForeground", "sidebar", 4.5)
    readable("toolbarControlForeground", "toolbarControlHover", 4.5)
    readable("terminalForeground", "terminalBackground", 7)
    readable("accent", "canvas", 3)
    readable("focus", "canvas", 3)
    readable("error", "canvas", 3)
    readable("warning", "canvas", 3)
    readable("terminalCursor", "terminalBackground", 3)

    # Status colors keep their meaning on any wallpaper. 14 is the 10 degree shift plus
    # what fitting a solved lightness into sRGB can add.
    error_hue = hue_of("#fb414a")
    warning_hue = hue_of("#fe9a00")
    if (hue_distance(hue_of(c["error"]), error_hue) > 14) fail("error is no longer red: " c["error"])
    if (hue_distance(hue_of(c["warning"]), warning_hue) > 14) fail("warning is no longer amber: " c["warning"])
    if (hue_distance(hue_of(c["searchMatchActiveBackground"]), hue_of("#eea52b")) > 14) fail("active search is no longer amber")
    if (hue_distance(hue_of(c["error"]), hue_of(c["warning"])) < 20) fail("error and warning hues are too close")
    if (chroma_of(c["error"]) < 0.1) fail("error is not colorful")
    if (chroma_of(c["warning"]) < 0.1) fail("warning is not colorful")

    # The elevation ladder climbs away from the canvas, in order.
    n = split("canvas surface surfaceOverlay accentSurface border input", ladder, " ")
    all_distinct("canvas surface surfaceOverlay accentSurface border input")
    previous = 0
    for (i = 1; i <= n; i++) {
        distance = abs(lightness_of(c[ladder[i]]) - lightness_of(c["canvas"]))
        if (distance < previous) fail(ladder[i] " is closer to the canvas than the step before it")
        previous = distance
    }
    all_distinct("sidebar sidebarRowHover sidebarRowActive sidebarRowSelected")
    if (appearance == "light" && lightness_of(c["border"]) >= lightness_of(c["canvas"])) fail("a light theme must build downward")

    if (name == "purple" && hue_distance(hue_of(c["error"]), error_hue) <= 5) fail("error does not lean toward the palette")
    if (name == "gray") {
        n = split("surface border input sidebarRowSelected", gray, " ")
        for (i = 1; i <= n; i++) if (chroma_of(c[gray[i]]) >= 0.01) fail(gray[i] " invents a tint on a gray wallpaper")
    }
    if (name == "red with one green" && hue_distance(hue_of(c["accent"]), 25) <= 20) fail("accent should avoid the error hue")
    if (name == "all red" && hue_distance(hue_of(seed), 25) > 5) fail("accent should keep the wallpaper when every color collides")

    exit failed
}
