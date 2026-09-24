"""Knoepfe der Flipdot-Anzeige."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PRIORITY_NORMAL, SOURCE_BUTTON
from .entity import FluepdotEntity
from .framebuffer import Framebuffer
from .render import raw_payload


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    controller = entry.runtime_data.controller
    async_add_entities(
        [
            FluepdotClearButton(controller),
            FluepdotDateButton(controller),
            FluepdotTestButton(controller),
            FluepdotInvertButton(controller),
            FluepdotExerciseButton(controller),
            FluepdotFluidButton(controller),
        ]
    )


class FluepdotClearButton(FluepdotEntity, ButtonEntity):
    """Anzeige leeren."""

    _attr_translation_key = "clear"
    _attr_icon = "mdi:eraser"

    def __init__(self, controller) -> None:
        super().__init__(controller, "clear")

    async def async_press(self) -> None:
        await self.controller.async_clear()


class FluepdotDateButton(FluepdotEntity, ButtonEntity):
    """Datum anzeigen - genau im gewohnten Format."""

    _attr_translation_key = "date"
    _attr_icon = "mdi:calendar"

    def __init__(self, controller) -> None:
        super().__init__(controller, "date")

    async def async_press(self) -> None:
        await self.controller.async_show(
            self.controller.date_payload(),
            priority=PRIORITY_NORMAL,
            source=SOURCE_BUTTON,
            page_id="datum",
        )


class FluepdotFluidButton(FluepdotEntity, ButtonEntity):
    """Die gewaehlte Fluessigkeits-Simulation (noch einmal) abspielen."""

    _attr_translation_key = "fluid"
    _attr_icon = "mdi:water"

    def __init__(self, controller) -> None:
        super().__init__(controller, "fluid")

    async def async_press(self) -> None:
        self.hass.async_create_task(self.controller.async_play_fluid())


class FluepdotTestButton(FluepdotEntity, ButtonEntity):
    """Testbild: Rahmen, Raster und Eckmarken."""

    _attr_translation_key = "test_pattern"
    _attr_icon = "mdi:grid"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller) -> None:
        super().__init__(controller, "test_pattern")

    async def async_press(self) -> None:
        width = self.controller.width
        height = self.controller.height
        buffer = Framebuffer(width, height)
        buffer.rect(0, 0, width, height)
        for x in range(0, width, 5):
            buffer.set(x, height // 2, 1)
        for y in range(0, height, 4):
            buffer.set(width // 2, y, 1)
        for corner_x, corner_y in ((0, 0), (width - 3, 0), (0, height - 3),
                                   (width - 3, height - 3)):
            buffer.rect(corner_x, corner_y, 3, 3, fill=True)
        await self.controller.async_show(
            raw_payload(buffer.to_ascii(), "Testbild"),
            priority=PRIORITY_NORMAL,
            duration=30,
            source=SOURCE_BUTTON,
        )


class FluepdotInvertButton(FluepdotEntity, ButtonEntity):
    """Aktuelles Bild invertieren."""

    _attr_translation_key = "invert"
    _attr_icon = "mdi:invert-colors"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller) -> None:
        super().__init__(controller, "invert")

    async def async_press(self) -> None:
        buffer = self.controller.last_framebuffer.copy()
        buffer.invert()
        await self.controller.async_show(
            raw_payload(buffer.to_ascii(), "Invertiert"),
            priority=PRIORITY_NORMAL,
            source=SOURCE_BUTTON,
        )


class FluepdotExerciseButton(FluepdotEntity, ButtonEntity):
    """Alle Punkte mehrfach durchklappen - gegen festsitzende Punkte."""

    _attr_translation_key = "exercise"
    _attr_icon = "mdi:dumbbell"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller) -> None:
        super().__init__(controller, "exercise")

    async def async_press(self) -> None:
        width = self.controller.width
        height = self.controller.height
        full = Framebuffer(width, height)
        full.clear(1)
        empty = Framebuffer(width, height)
        frames = []
        for _ in range(3):
            frames.append(full.copy())
            frames.append(empty.copy())
        await self.controller.async_animate(
            frames, 0.8, "Punkte-Training", PRIORITY_NORMAL
        )
