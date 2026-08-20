"""Der Kopf der Integration: Prioritaeten, Ruhezeit, Rotation, Schreiben.

Alles, was in Home Assistant auf die Anzeige will, laeuft hier durch. Damit
gibt es genau einen Schreiber, eine Warteschlange mit Prioritaeten und ein
hartes Ruhezeit-Gate.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .client import FluepdotClient, FluepdotError
from .const import (
    ALIGN_CENTER,
    DEFAULT_FONT,
    DEFAULT_QUIET_END,
    DEFAULT_QUIET_START,
    DEFAULT_ROTATION_INTERVAL,
    DISPLAY_MODE_DATE,
    DISPLAY_MODE_MANUAL,
    DISPLAY_MODE_OFF,
    DISPLAY_MODE_ROTATION,
    DOMAIN,
    MODE_COMPOSE,
    MODE_DEVICE,
    PRIORITY_BACKGROUND,
    PRIORITY_LEVEL,
    PRIORITY_NORMAL,
    SIGNAL_STATE_CHANGED,
    SOURCE_OFF,
    SOURCE_QUIET,
    SOURCE_ROTATION,
    STATE_STORAGE_KEY,
    STATE_STORAGE_VERSION,
)
from .fonts import FontRegistry
from .framebuffer import Framebuffer
from .pages import Page, load_pages_sync
from .render import Payload, blank_payload, text_payload

_LOGGER = logging.getLogger(__name__)

RETRY_WHEN_QUIET = 300
DATE_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
DATE_MONTHS = (
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
)


@dataclass
class Settings:
    """Was der Nutzer ueber Entities einstellt - ueberlebt Neustarts."""

    display_on: bool = True
    display_mode: str = DISPLAY_MODE_ROTATION
    quiet_enabled: bool = True
    quiet_start: str = DEFAULT_QUIET_START
    quiet_end: str = DEFAULT_QUIET_END
    default_font: str = DEFAULT_FONT
    align: str = ALIGN_CENTER
    rotation_interval: int = DEFAULT_ROTATION_INTERVAL
    set_delay_us: int = 1600
    differential: bool = False
    last_text: str = ""


@dataclass
class CurrentContent:
    """Was gerade auf der Anzeige steht."""

    description: str = "unbekannt"
    source: str = SOURCE_ROTATION
    priority: str = PRIORITY_BACKGROUND
    page_id: str | None = None
    expires_at: datetime | None = None
    written_at: datetime | None = None


@dataclass
class Diagnostics:
    """Zaehler fuer die Fehlersuche."""

    writes: int = 0
    suppressed_quiet: int = 0
    suppressed_priority: int = 0
    errors: int = 0
    last_error: str | None = None
    foreign_detections: int = 0


class FluepdotController:
    """Steuert die Anzeige."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: FluepdotClient,
        registry: FontRegistry,
        width: int,
        height: int,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.fonts = registry
        self.width = width
        self.height = height
        self.settings = Settings()
        self.current = CurrentContent()
        self.diagnostics = Diagnostics()
        self.pages: list[Page] = []
        self.device_fonts: list[str] = []
        self.available = True
        self.foreign_content = False
        self.last_framebuffer: Framebuffer = Framebuffer(width, height)
        self.pages_error: str | None = None

        self._store: Store = Store(
            hass, STATE_STORAGE_VERSION, f"{STATE_STORAGE_KEY}_{entry.entry_id}"
        )
        self._expected: str | None = None
        self._rotation_index = 0
        self._rotation_unsub = None
        self._expiry_unsub = None
        self._animation: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()
        self._started = False
        self._quiet_state = False
        self._tick_unsub = None

    # -- Lebenszyklus ------------------------------------------------------
    async def async_start(self) -> None:
        stored = await self._store.async_load()
        if stored:
            known = {f.name for f in Settings.__dataclass_fields__.values()}
            self.settings = Settings(
                **{key: value for key, value in stored.items() if key in known}
            )
        await self.async_reload_pages()
        try:
            fonts = await self.client.get_fonts()
            self.device_fonts = [short for _full, short in fonts]
        except FluepdotError as err:
            _LOGGER.warning("Schriftliste nicht lesbar: %s", err)
            self.device_fonts = [DEFAULT_FONT]
        self._quiet_state = self.quiet_now
        self._tick_unsub = async_track_time_interval(
            self.hass, self._handle_tick, timedelta(seconds=60)
        )
        self._started = True

    async def async_stop(self) -> None:
        self._started = False
        if self._tick_unsub:
            self._tick_unsub()
            self._tick_unsub = None
        self._cancel_rotation()
        self._cancel_expiry()
        self._cancel_animation()

    async def _save_settings(self) -> None:
        await self._store.async_save(asdict(self.settings))

    @callback
    def notify_listeners(self) -> None:
        async_dispatcher_send(
            self.hass, SIGNAL_STATE_CHANGED.format(self.entry.entry_id)
        )

    # -- Einstellungen -----------------------------------------------------
    async def async_update_settings(self, **changes) -> None:
        """Einstellung aendern, sichern und wirksam machen."""
        touched_display = False
        for key, value in changes.items():
            if not hasattr(self.settings, key):
                continue
            if getattr(self.settings, key) == value:
                continue
            setattr(self.settings, key, value)
            if key in ("display_on", "display_mode", "rotation_interval"):
                touched_display = True
            if key == "differential":
                await self._apply_rendering_mode(value)
            if key == "set_delay_us":
                await self._apply_timings(value)
        await self._save_settings()
        self.notify_listeners()
        if touched_display:
            await self.async_refresh_display(force=True)

    async def _apply_rendering_mode(self, differential: bool) -> None:
        try:
            await self.client.set_rendering_mode(1 if differential else 0)
        except FluepdotError as err:
            self._record_error(err)

    async def _apply_timings(self, set_delay_us: int) -> None:
        steps = max(1, min(1200, int(round(set_delay_us / 50))))
        try:
            await self.client.set_timings([(0, steps, steps)] * self.width)
        except FluepdotError as err:
            self._record_error(err)

    # -- Ruhezeit ----------------------------------------------------------
    @property
    def quiet_now(self) -> bool:
        """Liegt die aktuelle Zeit in der Ruhezeit?"""
        if not self.settings.quiet_enabled:
            return False
        start = _parse_time(self.settings.quiet_start)
        end = _parse_time(self.settings.quiet_end)
        if start == end:
            return False
        now = dt_util.now().time()
        if start < end:
            return start <= now < end
        return now >= start or now < end

    # -- Anzeigen ----------------------------------------------------------
    async def async_show(
        self,
        payload: Payload,
        priority: str = PRIORITY_NORMAL,
        duration: float | None = None,
        source: str = "service",
        page_id: str | None = None,
    ) -> bool:
        """Payload anzeigen, sofern Ruhezeit und Prioritaet es zulassen."""
        if not self._started:
            return False

        if not self.settings.display_on:
            # Bei ausgeschalteter Anzeige wird ueberhaupt nichts geschrieben.
            self.diagnostics.suppressed_priority += 1
            return False

        if self.quiet_now:
            self.diagnostics.suppressed_quiet += 1
            self.current.source = SOURCE_QUIET
            self.current.description = f"Ruhezeit - unterdrueckt: {payload.summary()}"
            self.notify_listeners()
            _LOGGER.debug("Ruhezeit aktiv, Anzeige unterdrueckt: %s", payload.summary())
            return False

        if not self._may_replace(priority):
            self.diagnostics.suppressed_priority += 1
            return False

        summary = payload.summary()
        unchanged = (
            priority == PRIORITY_BACKGROUND
            and duration is None
            and source == self.current.source
            and page_id == self.current.page_id
            and summary == self.current.description
        )
        if unchanged:
            # Gleicher Inhalt wie zuletzt geschrieben (z. B. dieselbe
            # Rotationsseite mit unveraendertem Text, oder der Datum-Modus an
            # einem Tag ohne Datumswechsel). Nicht erneut aufs Geraet
            # schreiben - das wuerde die Klappmagnete grundlos klappern
            # lassen, obwohl sich am Bild nichts aendert. Der Aufrufer
            # (Rotation) plant den naechsten Check selbst neu ein.
            return True

        self._cancel_animation()
        written = await self._write(payload)
        if not written:
            return False

        self._cancel_expiry()
        self.current = CurrentContent(
            description=summary,
            source=source,
            priority=priority,
            page_id=page_id,
            written_at=dt_util.utcnow(),
        )
        if duration:
            self.current.expires_at = dt_util.utcnow() + timedelta(seconds=duration)
            self._expiry_unsub = async_call_later(
                self.hass, duration, self._handle_expiry
            )
            self._cancel_rotation()
        elif priority == PRIORITY_BACKGROUND:
            self._schedule_rotation()
        else:
            self._cancel_rotation()

        self.notify_listeners()
        return True

    def _may_replace(self, priority: str) -> bool:
        """Darf die neue Nachricht die aktuelle verdraengen?"""
        if self.current.expires_at is None:
            return True
        if self.current.expires_at <= dt_util.utcnow():
            return True
        return PRIORITY_LEVEL.get(priority, 0) >= PRIORITY_LEVEL.get(
            self.current.priority, 0
        )

    async def _write(self, payload: Payload) -> bool:
        """Payload tatsaechlich aufs Geraet schreiben."""
        async with self._write_lock:
            try:
                if payload.mode == MODE_DEVICE and not payload.wants_compose():
                    text, font, x, y = payload.device_call(self.settings.default_font)
                    if payload.clear:
                        await self.client.clear(self.width, self.height)
                    await self.client.post_text(text, font, x, y)
                else:
                    buffer = payload.compose(self.fonts, self.width, self.height)
                    await self.client.post_framebuffer(buffer.to_ascii())
                    self.last_framebuffer = buffer
                    self._expected = buffer.to_ascii()

                self.diagnostics.writes += 1
                self.available = True
                if payload.mode == MODE_DEVICE:
                    # Das Geraet hat selbst gerendert - Ergebnis zurueckholen,
                    # damit Vorschau und Fremdinhalts-Erkennung stimmen.
                    await self._sync_from_device()
                self.foreign_content = False
            except FluepdotError as err:
                self._record_error(err)
                return False
        return True

    async def _sync_from_device(self) -> None:
        try:
            raw = await self.client.get_framebuffer()
        except FluepdotError as err:
            _LOGGER.debug("Framebuffer nach dem Schreiben nicht lesbar: %s", err)
            return
        self._expected = raw
        self.last_framebuffer = Framebuffer.from_ascii(raw, self.width, self.height)

    def _record_error(self, err: Exception) -> None:
        self.diagnostics.errors += 1
        self.diagnostics.last_error = str(err)
        self.available = False
        _LOGGER.warning("Flipdot nicht erreichbar: %s", err)
        self.notify_listeners()

    # -- Rotation ----------------------------------------------------------
    async def async_reload_pages(self) -> None:
        path = self.hass.config.path("fluepdot_pages.yaml")
        try:
            self.pages = await self.hass.async_add_executor_job(load_pages_sync, path)
            self.pages_error = None
        except Exception as err:  # noqa: BLE001
            self.pages_error = str(err)
            _LOGGER.error("fluepdot_pages.yaml ist fehlerhaft: %s", err)
            self.pages = []
        self._rotation_index = 0
        self.notify_listeners()

    @property
    def visible_pages(self) -> list[Page]:
        return [page for page in self.pages if page.is_visible(self.hass)]

    def page_by_id(self, page_id: str) -> Page | None:
        for page in self.pages:
            if page.page_id == page_id:
                return page
        return None

    async def async_refresh_display(self, force: bool = False) -> None:
        """Grundzustand herstellen (Rotation, Datum, Aus oder Manuell)."""
        if not self._started:
            return

        if not self.settings.display_on or self.settings.display_mode == DISPLAY_MODE_OFF:
            self._cancel_rotation()
            self._cancel_expiry()
            if self.quiet_now:
                return
            async with self._write_lock:
                try:
                    await self.client.clear(self.width, self.height)
                    self.last_framebuffer = Framebuffer(self.width, self.height)
                    self._expected = self.last_framebuffer.to_ascii()
                    self.diagnostics.writes += 1
                    self.available = True
                except FluepdotError as err:
                    self._record_error(err)
            self.current = CurrentContent(
                description="Anzeige aus",
                source=SOURCE_OFF,
                priority=PRIORITY_BACKGROUND,
                written_at=dt_util.utcnow(),
            )
            self.notify_listeners()
            return

        if self.settings.display_mode == DISPLAY_MODE_MANUAL and not force:
            return

        if self.settings.display_mode == DISPLAY_MODE_DATE:
            await self.async_show(
                self.date_payload(),
                priority=PRIORITY_BACKGROUND,
                source=SOURCE_ROTATION,
                page_id="datum",
            )
            self._schedule_rotation(self.settings.rotation_interval)
            return

        if self.settings.display_mode == DISPLAY_MODE_MANUAL:
            if self.settings.last_text:
                await self.async_show(
                    text_payload(
                        self.settings.last_text,
                        font=self.settings.default_font,
                        align=self.settings.align,
                    ),
                    priority=PRIORITY_BACKGROUND,
                    source="text",
                )
            return

        await self._show_next_page()

    async def _show_next_page(self) -> None:
        pages = self.visible_pages
        if not pages:
            # Keine Seite aktiv - dann wenigstens das Datum, wie bisher.
            await self.async_show(
                self.date_payload(),
                priority=PRIORITY_BACKGROUND,
                source=SOURCE_ROTATION,
                page_id="datum",
            )
            self._schedule_rotation(self.settings.rotation_interval)
            return

        self._rotation_index %= len(pages)
        page = pages[self._rotation_index]
        self._rotation_index = (self._rotation_index + 1) % len(pages)

        payload = page.build(self.hass)
        if payload is None:
            self._schedule_rotation(5)
            return

        shown = await self.async_show(
            payload,
            priority=PRIORITY_BACKGROUND,
            source=SOURCE_ROTATION,
            page_id=page.page_id,
        )
        delay = page.duration or self.settings.rotation_interval
        self._schedule_rotation(delay if shown else RETRY_WHEN_QUIET)

    def _schedule_rotation(self, delay: float | None = None) -> None:
        self._cancel_rotation()
        if not self._started or not self.settings.display_on:
            return
        if self.settings.display_mode in (DISPLAY_MODE_MANUAL, DISPLAY_MODE_OFF):
            return
        seconds = delay or self.settings.rotation_interval
        self._rotation_unsub = async_call_later(
            self.hass, max(5, seconds), self._handle_rotation
        )

    @callback
    def _cancel_rotation(self) -> None:
        if self._rotation_unsub:
            self._rotation_unsub()
            self._rotation_unsub = None

    @callback
    def _cancel_expiry(self) -> None:
        if self._expiry_unsub:
            self._expiry_unsub()
            self._expiry_unsub = None

    @callback
    def _cancel_animation(self) -> None:
        if self._animation and not self._animation.done():
            self._animation.cancel()
        self._animation = None

    async def _handle_rotation(self, _now) -> None:
        self._rotation_unsub = None
        if self.settings.display_mode == DISPLAY_MODE_DATE:
            shown = await self.async_show(
                self.date_payload(),
                priority=PRIORITY_BACKGROUND,
                source=SOURCE_ROTATION,
                page_id="datum",
            )
            self._schedule_rotation(
                self.settings.rotation_interval if shown else RETRY_WHEN_QUIET
            )
            return
        await self._show_next_page()

    async def _handle_tick(self, _now) -> None:
        """Minuetlich pruefen, ob die Ruhezeit beginnt oder endet."""
        quiet = self.quiet_now
        if quiet == self._quiet_state:
            return
        self._quiet_state = quiet
        self.notify_listeners()
        if not quiet:
            # Ruhezeit vorbei - normalen Betrieb wieder aufnehmen.
            await self.async_refresh_display(force=True)

    async def _handle_expiry(self, _now) -> None:
        self._expiry_unsub = None
        self.current.expires_at = None
        await self.async_refresh_display(force=True)

    # -- Fertige Inhalte ---------------------------------------------------
    def date_payload(self) -> Payload:
        """Das Datum, exakt im bisherigen Format."""
        now = dt_util.now()
        text = (
            f"{DATE_WEEKDAYS[now.weekday()]}, {now.day}. {DATE_MONTHS[now.month - 1]}"
        )
        return Payload(
            kind="text",
            text=text,
            font=DEFAULT_FONT,
            mode=MODE_DEVICE,
            description=f"Datum: {text}",
        )

    async def async_clear(self) -> bool:
        return await self.async_show(
            blank_payload(), priority=PRIORITY_NORMAL, source="service"
        )

    # -- Animationen -------------------------------------------------------
    async def async_animate(
        self,
        frames: list[Framebuffer],
        delay: float,
        description: str,
        priority: str = PRIORITY_NORMAL,
    ) -> None:
        """Eine Folge von Bildern abspielen."""
        if self.quiet_now or not self.settings.display_on:
            self.diagnostics.suppressed_quiet += 1
            return
        if not self._may_replace(priority):
            self.diagnostics.suppressed_priority += 1
            return

        self._cancel_animation()
        self._cancel_expiry()
        self._cancel_rotation()
        self.current = CurrentContent(
            description=description,
            source="service",
            priority=priority,
            written_at=dt_util.utcnow(),
        )
        self.notify_listeners()

        async def runner() -> None:
            try:
                for frame in frames:
                    if self.quiet_now:
                        break
                    async with self._write_lock:
                        try:
                            await self.client.post_framebuffer(frame.to_ascii())
                            self.last_framebuffer = frame
                            self._expected = frame.to_ascii()
                            self.diagnostics.writes += 1
                        except FluepdotError as err:
                            self._record_error(err)
                            return
                    await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            finally:
                self.notify_listeners()

        self._animation = self.hass.async_create_task(runner())
        try:
            await self._animation
        except asyncio.CancelledError:
            pass
        finally:
            self._animation = None
            await self.async_refresh_display(force=True)

    # -- Vom Koordinator ---------------------------------------------------
    @callback
    def handle_poll(self, raw: str | None, error: str | None) -> None:
        """Ergebnis des regelmaessigen Abrufs verarbeiten."""
        if error:
            self.available = False
            self.diagnostics.last_error = error
            return
        self.available = True
        if raw is None:
            return
        changed = raw.rstrip("\n") != self.last_framebuffer.to_ascii().rstrip("\n")
        self.last_framebuffer = Framebuffer.from_ascii(raw, self.width, self.height)
        was_foreign = self.foreign_content
        if self._expected is not None and raw.rstrip("\n") != self._expected.rstrip("\n"):
            if not self.foreign_content:
                self.diagnostics.foreign_detections += 1
                _LOGGER.debug("Fremder Inhalt auf der Anzeige erkannt")
            self.foreign_content = True
        else:
            self.foreign_content = False
        if changed or was_foreign != self.foreign_content:
            # Vorschau und Sensoren nachziehen, auch wenn jemand anderes
            # geschrieben hat (etwa die Weboberflaeche flipdot-web).
            self.notify_listeners()


def _parse_time(value: str) -> time:
    try:
        parts = [int(part) for part in value.split(":")]
        while len(parts) < 3:
            parts.append(0)
        return time(parts[0] % 24, parts[1] % 60, parts[2] % 60)
    except (ValueError, AttributeError):
        return time(0, 0)
