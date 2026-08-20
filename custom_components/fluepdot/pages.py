"""Rotationsseiten aus /config/fluepdot_pages.yaml.

Jede Seite beschreibt per Jinja-Template, was angezeigt werden soll. Die Datei
wird beim ersten Start angelegt und enthaelt dann genau eine Seite: das Datum,
exakt so wie es die Anzeige bisher zeigte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template

from .const import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    MODE_COMPOSE,
    MODE_DEVICE,
    VALIGN_MIDDLE,
)
from .render import Payload

_LOGGER = logging.getLogger(__name__)

DEFAULT_PAGES_YAML = '''# Rotationsseiten der Flipdot-Anzeige
#
# Diese Datei wurde von der Integration "Flipdot (fluepdot)" angelegt.
# Nach Aenderungen: Aktion  fluepdot.reload_pages  aufrufen - kein Neustart noetig.
#
# Felder je Seite:
#   id         eindeutiger Schluessel (Pflicht)
#   name       Anzeigename fuer sensor.flipdot_inhalt
#   enabled    true/false
#   duration   Anzeigedauer in Sekunden (Default: number.flipdot_rotationsdauer)
#   mode       device  = die Anzeige rendert den Text selbst (wie bisher)
#              compose = Home Assistant baut das Bild komplett auf
#              (nur compose kann zentrieren, mehrzeilig, Balken und Symbole)
#   font       Schriftname; bei compose zusaetzlich "builtin5x7" moeglich
#   align      left | center | right      valign  top | middle | bottom
#   condition  Jinja-Template; Seite wird nur gezeigt, wenn es wahr ergibt
#   text       Jinja-Template mit dem Text
#   lines      Liste von Jinja-Templates (eine je Zeile, compose)
#   icon       Symbol links neben dem Text (compose): sun cloud rain snow bolt
#              house bin bell drop check cross arrow_up arrow_down person washer
#   bar        Balken: value/min/max (Templates) plus x y width height

pages:
  # --- Standard: das Datum, unveraendert wie seit Jahren -------------------
  - id: datum
    name: Datum
    enabled: true
    duration: 60
    mode: device
    font: DejaVuSans12bw_bwfont
    text: >
      {% set tage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"] %}
      {% set monate = ["Januar","Februar","Maerz","April","Mai","Juni","Juli",
                       "August","September","Oktober","November","Dezember"] %}
      {{ tage[now().weekday()] }}, {{ now().day }}. {{ monate[now().month - 1] }}

  # --- Vorlagen: bei Bedarf enabled auf true setzen ------------------------
  - id: uhr
    name: Uhr und Datum
    enabled: false
    duration: 30
    mode: compose
    font: builtin5x7
    align: center
    lines:
      - "{{ now().strftime('%H:%M') }}"
      - >
        {% set tage = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag",
                       "Samstag","Sonntag"] %}
        {{ tage[now().weekday()] }}, {{ now().strftime('%d.%m.') }}

  - id: muell
    name: Abfuhr
    enabled: false
    duration: 30
    mode: compose
    font: builtin5x7
    align: center
    icon: bin
    condition: "{{ states('sensor.abfallnext') | int(99) <= 2 }}"
    lines:
      - >
        {% set tonnen = [
             ('Restmuell',   states('sensor.abfallnextrestmull')   | int(999)),
             ('Altpapier',   states('sensor.abfallnextaltpapier')  | int(999)),
             ('Gelber Sack', states('sensor.abfallnextgelbersack') | int(999)),
             ('Biomuell',    states('sensor.abfallnextbiomull')    | int(999)) ] %}
        {{ (tonnen | sort(attribute='1') | first)[0] }}
      - >
        {% set tage = states('sensor.abfallnext') | int(99) %}
        {{ 'heute raus' if tage == 0
           else ('morgen raus' if tage == 1 else 'in ' ~ tage ~ ' Tagen') }}

  - id: wetter
    name: Wetter
    enabled: false
    duration: 30
    mode: compose
    font: builtin5x7
    align: center
    lines:
      - "{{ state_attr('weather.siekfeld','temperature') | round(0) }} Grad draussen"
      - "{{ states('weather.siekfeld') }}"

  - id: strom
    name: Strom
    enabled: false
    duration: 30
    mode: compose
    font: builtin5x7
    align: center
    lines:
      - "PV {{ (states('sensor.pv_null') | float(0) / 1000) | round(1) }} kW"
      - >
        {% set netz = states('sensor.momentan_verbrauch') | float(0) %}
        {{ 'Einspeisung' if netz < 0 else 'Bezug' }} {{ (netz | abs / 1000) | round(1) }} kW
    bar:
      value: "{{ [states('sensor.pv_null') | float(0), 10000] | min }}"
      min: 0
      max: 10000
      x: 0
      y: 13
      width: 115
      height: 3

  - id: waesche
    name: Waesche fertig
    enabled: false
    duration: 20
    mode: compose
    font: builtin5x7
    align: center
    icon: washer
    condition: "{{ is_state('sensor.waschmaschine_state', 'finished') }}"
    lines:
      - "Waesche ist fertig"
'''


@dataclass(slots=True)
class Page:
    """Eine Rotationsseite."""

    page_id: str
    name: str
    enabled: bool = True
    duration: int | None = None
    mode: str = MODE_DEVICE
    font: str | None = None
    align: str = ALIGN_LEFT
    valign: str = VALIGN_MIDDLE
    condition: str | None = None
    text: str | None = None
    lines: list[str] = field(default_factory=list)
    icon: str | None = None
    icon_x: int = 0
    icon_y: int = 4
    bar: dict[str, Any] | None = None

    def _render_template(self, hass: HomeAssistant, raw: str) -> str:
        template = Template(raw, hass)
        value = template.async_render(parse_result=False)
        return str(value).strip()

    def is_visible(self, hass: HomeAssistant) -> bool:
        if not self.enabled:
            return False
        if not self.condition:
            return True
        try:
            result = self._render_template(hass, self.condition)
        except TemplateError as err:
            _LOGGER.warning("Bedingung der Seite %s ist fehlerhaft: %s", self.page_id, err)
            return False
        return result.lower() in ("true", "1", "on", "yes")

    def build(self, hass: HomeAssistant) -> Payload | None:
        """Seite zu einem Payload rendern."""
        try:
            text = self._render_template(hass, self.text) if self.text else ""
            lines = [self._render_template(hass, line) for line in self.lines]
        except TemplateError as err:
            _LOGGER.warning("Seite %s laesst sich nicht rendern: %s", self.page_id, err)
            return None

        lines = [line for line in lines if line]
        if not text and not lines:
            return None

        payload = Payload(
            kind="lines" if lines else "text",
            text=text,
            lines=lines,
            font=self.font,
            align=self.align,
            valign=self.valign,
            mode=self.mode,
            description=self.name,
        )

        if self.icon:
            icon_name, icon_x, icon_y = self.icon, self.icon_x, self.icon_y
            payload.ops.append(
                lambda buffer: buffer.draw_icon(icon_name, icon_x, icon_y)
            )
            payload.mode = MODE_COMPOSE

        if self.bar:
            spec = dict(self.bar)
            try:
                value = float(self._render_template(hass, str(spec.get("value", "0"))))
                minimum = float(self._render_template(hass, str(spec.get("min", 0))))
                maximum = float(self._render_template(hass, str(spec.get("max", 100))))
            except (TemplateError, ValueError) as err:
                _LOGGER.warning("Balken der Seite %s ist fehlerhaft: %s", self.page_id, err)
            else:
                span = maximum - minimum
                fraction = 0.0 if span <= 0 else (value - minimum) / span
                bar_x = int(spec.get("x", 0))
                bar_y = int(spec.get("y", 12))
                bar_w = int(spec.get("width", 115))
                bar_h = int(spec.get("height", 3))
                border = bool(spec.get("border", True))
                payload.ops.append(
                    lambda buffer: buffer.draw_bar(
                        bar_x, bar_y, bar_w, bar_h, fraction, border
                    )
                )
                payload.mode = MODE_COMPOSE

        return payload


def _as_page(raw: dict[str, Any]) -> Page | None:
    page_id = str(raw.get("id") or "").strip()
    if not page_id:
        _LOGGER.warning("Seite ohne 'id' wird uebersprungen")
        return None
    lines = raw.get("lines") or []
    if isinstance(lines, str):
        lines = [lines]
    mode = str(raw.get("mode", MODE_DEVICE)).lower()
    if mode not in (MODE_DEVICE, MODE_COMPOSE):
        mode = MODE_DEVICE
    return Page(
        page_id=page_id,
        name=str(raw.get("name") or page_id),
        enabled=bool(raw.get("enabled", True)),
        duration=int(raw["duration"]) if raw.get("duration") else None,
        mode=mode,
        font=raw.get("font"),
        align=str(raw.get("align", ALIGN_CENTER if mode == MODE_COMPOSE else ALIGN_LEFT)),
        valign=str(raw.get("valign", VALIGN_MIDDLE)),
        condition=raw.get("condition"),
        text=raw.get("text"),
        lines=[str(line) for line in lines],
        icon=raw.get("icon"),
        icon_x=int(raw.get("icon_x", 0)),
        icon_y=int(raw.get("icon_y", 4)),
        bar=raw.get("bar"),
    )


def ensure_pages_file(path: str) -> bool:
    """Datei anlegen, falls sie fehlt. Liefert True, wenn neu erstellt."""
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(DEFAULT_PAGES_YAML)
    return True


def load_pages_sync(path: str) -> list[Page]:
    """Seiten aus der YAML-Datei lesen (blockierend, im Executor aufrufen)."""
    from homeassistant.util.yaml import load_yaml

    ensure_pages_file(path)
    data = load_yaml(path) or {}
    if not isinstance(data, dict):
        raise ValueError("fluepdot_pages.yaml muss eine Zuordnung mit 'pages' sein")
    raw_pages = data.get("pages") or []
    if not isinstance(raw_pages, list):
        raise ValueError("'pages' muss eine Liste sein")
    pages: list[Page] = []
    for entry in raw_pages:
        if not isinstance(entry, dict):
            continue
        page = _as_page(entry)
        if page:
            pages.append(page)
    return pages
