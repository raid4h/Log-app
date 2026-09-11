# palettes.py
#
# Each theme is a dictionary mapping a SEMANTIC TOKEN (a plain string
# describing a role, e.g. "background") to the hex color that role
# should have in that theme.
#
# The token names below must be IDENTICAL across every theme dict.
# That's what lets ThemeManager swap themes safely: it just looks up
# the same token in a different dictionary.

# This is the APP'S DEFAULT theme (formerly "Cream") — soft cream/tan
# base with warm brown accents.
DEFAULT = {
    "background":      "#FBF3E4",
    "card_primary":    "#F1E4D0",
    "card_secondary":  "#E8D8C0",
    "border":          "#D9C4A5",
    "accent":          "#9C6B2E",  # deepened from #C8A97E -- old accent was nearly the same lightness as card_primary/card_secondary, so section labels (e.g. "Backup & Restore") were low-contrast/hard to read on either card.
    "text_secondary":  "#8A6F53",
    "button":          "#6B4A32",
    "text_primary":    "#3B2A1D",
    "button_text":     "#FBF3E4",
    "tile_accent_tasks":    "#2C4A7C",   # navy for tasks icon
}

# DARK theme — purple family restored per your preference, but
# rebuilt with a proper Discord-style elevation ladder (each surface
# level distinctly LIGHTER than the last, same convention as before)
# and a corrected text_secondary. The previous purple dark theme's
# real bug: text_secondary (#553A84) was DARKER than background
# (#222238) -- backwards for "secondary text on a dark background,"
# so it was nearly invisible in places. Fixed by making
# text_secondary a light lavender-gray instead.
DARK = {
    "background":      "#1A1826",  # darkest surface
    "card_primary":    "#241F35",  # mid surface
    "card_secondary":  "#2E2844",  # lightest surface -- main content level
    "border":          "#3F3859",  # subtle purple-gray divider
    "accent":          "#8B7FD1",  # light periwinkle-purple, Discord-blurple role but purple
    "text_secondary":  "#B4ACC7",  # light lavender-gray -- always legible on every surface above
    "button":          "#7B6CE0",  # saturated purple primary-action button
    "text_primary":    "#F0EDF7",  # near-white with a faint purple tint
    "button_text":     "#FFFFFF",

    "tile_accent_tasks":    "#7D9FD1",   # lighter navy, as requested
}

# Floral theme (formerly the app's default) — periwinkle-lavender base
# with soft pink/coral accents.
FLORAL = {
    "background":      "#DCD6F5",
    "card_primary":    "#F8F5FC",
    "card_secondary":  "#F5C7DC",
    "border":          "#B9AEE8",
    "accent":          "#B23A6B",  # deepened from #F2A6B4 -- old accent nearly matched card_secondary's pink, so section labels (e.g. "Privacy") were washing out on that card.
    "text_secondary":  "#8A7FA8",
    "button":          "#D6567A",
    "text_primary":    "#4A3B6B",
    "button_text":     "#FFF9FC",

    "tile_accent_tasks":    "#5C7FB0",
}

MONOCHROME = {
    "background":      "#121212",
    "card_primary":    "#242424",
    "card_secondary":  "#303030",
    "border":          "#4A4A4A",
    "accent":          "#B0B0B0",
    "text_secondary":  "#BDBDBD",
    "button":          "#E0E0E0",
    "text_primary":    "#FFFFFF",
    "button_text":     "#121212",

    "tile_accent_tasks":    "#B0B0B0",
}

MATCHA = {
    "background":      "#C9D3B4",
    "card_primary":    "#F4EFDD",
    "card_secondary":  "#E9E2C8",
    "border":          "#B7C29B",
    "accent":          "#7C9A5E",
    "text_secondary":  "#6E7A58",
    "button":          "#5C7A44",
    "text_primary":    "#3A4530",
    "button_text":     "#F5F1E6",

    "tile_accent_tasks":    "#3E5A73",   # a muted blue that sits comfortably next to matcha's greens
}

# --- Semantic token constants ---
# These are just the *names* of the roles — plain strings, not colors.
# Existing code that imports these (like every themed screen's
# THEME_MAP) does not need to change at all.

BACKGROUND      = "background"
CARD_PRIMARY    = "card_primary"
CARD_SECONDARY  = "card_secondary"
TEXT_PRIMARY    = "text_primary"
TEXT_SECONDARY  = "text_secondary"
BUTTON          = "button"
BUTTON_TEXT     = "button_text"
BORDER          = "border"
ACCENT          = "accent"

TILE_ACCENT_TASKS    = "tile_accent_tasks"