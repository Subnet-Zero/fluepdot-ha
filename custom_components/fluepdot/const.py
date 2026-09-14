"""Konstanten der Flipdot-Integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "fluepdot"

# --- Konfiguration ---------------------------------------------------------
CONF_HOST: Final = "host"
CONF_WIDTH: Final = "width"
CONF_HEIGHT: Final = "height"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_DEFAULT_FONT: Final = "default_font"
CONF_ROTATION_INTERVAL: Final = "rotation_interval"
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_QUIET_ENABLED: Final = "quiet_enabled"

DEFAULT_WIDTH: Final = 115
DEFAULT_HEIGHT: Final = 16
DEFAULT_SCAN_INTERVAL: Final = 30
DEFAULT_ROTATION_INTERVAL: Final = 60
DEFAULT_FONT: Final = "DejaVuSans12bw_bwfont"
DEFAULT_QUIET_START: Final = "22:00:00"
DEFAULT_QUIET_END: Final = "06:30:00"
DEFAULT_TIMEOUT: Final = 8

# Das Geraet ist immer 16 Zeilen hoch (Firmware-Vorgabe).
FIXED_HEIGHT: Final = 16

# --- Rendering -------------------------------------------------------------
MODE_DEVICE: Final = "device"
MODE_COMPOSE: Final = "compose"
RENDER_MODES: Final = [MODE_DEVICE, MODE_COMPOSE]

ALIGN_LEFT: Final = "left"
ALIGN_CENTER: Final = "center"
ALIGN_RIGHT: Final = "right"
ALIGNMENTS: Final = [ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT]

# --- Zielanzeige (destination_sign) ----------------------------------------
BOX_OUTLINE: Final = "outline"
BOX_FILLED: Final = "filled"
BOX_NONE: Final = "none"
BOX_STYLES: Final = [BOX_OUTLINE, BOX_FILLED, BOX_NONE]

DEFAULT_VIA_PREFIX: Final = "über"

VALIGN_TOP: Final = "top"
VALIGN_MIDDLE: Final = "middle"
VALIGN_BOTTOM: Final = "bottom"
VALIGNMENTS: Final = [VALIGN_TOP, VALIGN_MIDDLE, VALIGN_BOTTOM]

RENDERING_MODE_FULL: Final = 0
RENDERING_MODE_DIFFERENTIAL: Final = 1

# --- Anzeigemodi (select.flipdot_modus) ------------------------------------
DISPLAY_MODE_ROTATION: Final = "rotation"
DISPLAY_MODE_DATE: Final = "date"
DISPLAY_MODE_MANUAL: Final = "manual"
DISPLAY_MODE_OFF: Final = "off"
DISPLAY_MODES: Final = [
    DISPLAY_MODE_ROTATION,
    DISPLAY_MODE_DATE,
    DISPLAY_MODE_MANUAL,
    DISPLAY_MODE_OFF,
]

# --- Prioritaeten ----------------------------------------------------------
PRIORITY_BACKGROUND: Final = "background"
PRIORITY_NORMAL: Final = "normal"
PRIORITY_HIGH: Final = "high"
PRIORITY_ALARM: Final = "alarm"
PRIORITIES: Final = [
    PRIORITY_BACKGROUND,
    PRIORITY_NORMAL,
    PRIORITY_HIGH,
    PRIORITY_ALARM,
]
PRIORITY_LEVEL: Final = {
    PRIORITY_BACKGROUND: 0,
    PRIORITY_NORMAL: 10,
    PRIORITY_HIGH: 20,
    PRIORITY_ALARM: 30,
}

# --- Services --------------------------------------------------------------
SERVICE_SEND_TEXT: Final = "send_text"
SERVICE_SEND_LINES: Final = "send_lines"
SERVICE_MARQUEE: Final = "marquee"
SERVICE_DRAW: Final = "draw"
SERVICE_DRAW_BAR: Final = "draw_bar"
SERVICE_SET_PIXEL: Final = "set_pixel"
SERVICE_CLEAR_PIXEL: Final = "clear_pixel"
SERVICE_CLEAR: Final = "clear"
SERVICE_EFFECT: Final = "effect"
SERVICE_SHOW_PAGE: Final = "show_page"
SERVICE_RELOAD_PAGES: Final = "reload_pages"
SERVICE_EXTRACT_FONTS: Final = "extract_fonts"
SERVICE_SET_TIMINGS: Final = "set_rendering_timings"
SERVICE_DESTINATION_SIGN: Final = "destination_sign"

EFFECTS: Final = ["wipe", "dissolve", "matrix", "blink", "snow", "invert"]

# --- Dateien ---------------------------------------------------------------
PAGES_FILE: Final = "fluepdot_pages.yaml"
FONTS_STORAGE_KEY: Final = "fluepdot_fonts"
FONTS_STORAGE_VERSION: Final = 1
STATE_STORAGE_KEY: Final = "fluepdot_state"
STATE_STORAGE_VERSION: Final = 1

# --- Signale ---------------------------------------------------------------
SIGNAL_STATE_CHANGED: Final = "fluepdot_state_changed_{}"

# --- Quellen (fuer sensor.flipdot_inhalt) ----------------------------------
SOURCE_ROTATION: Final = "rotation"
SOURCE_SERVICE: Final = "service"
SOURCE_TEXT_ENTITY: Final = "text"
SOURCE_NOTIFY: Final = "notify"
SOURCE_BUTTON: Final = "button"
SOURCE_FOREIGN: Final = "foreign"
SOURCE_OFF: Final = "off"
SOURCE_QUIET: Final = "quiet"
