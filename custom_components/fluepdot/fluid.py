"""Fluessigkeits-Simulationen fuer die Flipdot-Anzeige.

115x16 Punkte, jeder nur an oder aus - da hilft keine Navier-Stokes-Loesung,
sondern Modelle, die bei dieser Aufloesung nach Wasser *aussehen*:

- Teilchenwasser (``_Pool``, fuer den Abfluss): ein Zellularautomat, in dem
  jeder Punkt ein Tropfen ist. Tropfen fallen mit wachsender Geschwindigkeit, rutschen
  seitlich ab, behalten beim Aufprall etwas Schwung und spritzen bei hartem
  Aufprall als freie Tropfen hoch. Liegt Wasser ruhig, bleibt es liegen -
  sonst wuerden die Klappmagnete die ganze Zeit grundlos klappern.
- Hoehenfeld (``_Surface``): eine Wasseroberflaeche als Saeulenhoehen, die
  ueber das "virtual pipes"-Modell miteinander Wasser austauschen. In flachem
  Wasser leiten die Rohre schwaecher - Wellen laufen dort langsamer, holen
  sich von hinten ein und steilen sich auf, wie am Strand. Dazu kommen frei
  fliegende Tropfen (Strahl, Regen, Spritzer, Gischt), die beim Eintauchen
  ihr Volumen und ihren Schwung an die Oberflaeche abgeben.
- 2D-Wellengleichung fuer die Draufsicht auf einen Teich.

Jede Simulation erzaehlt eine kleine Geschichte (Wasser kommt, bewegt sich,
laeuft ab) und endet mit leerer Tafel. Sie rechnet Schritt fuer Schritt, und
aus allen Schritten werden gleichmaessig so viele Bilder gezogen, wie die
gewuenschte Dauer hergibt. Alles reines Python.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
import math
import random

from .const import (
    FLUID_DAM_BREAK,
    FLUID_DRAIN,
    FLUID_FOUNTAIN,
    FLUID_POUR,
    FLUID_RAIN,
    FLUID_RIPPLE,
    FLUID_SLOSH,
    FLUID_SURPRISE,
    FLUID_WAVE,
)
from .framebuffer import Framebuffer

EMPTY = 0
WATER = 1
WALL = 2

MAX_FALL = 3  # Zellen pro Schritt, schneller faellt kein Tropfen
REACH = 16  # so weit sucht ruhendes Wasser seitlich nach einer tieferen Stelle
GLIDE = 3  # so viele Zellen gleitet es pro Schritt dorthin
FLOW = 10  # so viele Schritte fliesst frisch gefallenes Wasser seitlich weiter
GRAVITY = 0.3  # fuer frei fliegende Tropfen, Zellen pro Schritt^2
DRY = 1e-3  # darunter gilt eine Saeule als trocken
CFL = 0.45  # Sicherheitsfaktor fuer die Zeitschritte des Flachwassers

# 0 -> aus, alles andere (Wasser, Wand) -> an.
_ON = bytes([0] + [1] * 255)


class _Pool:
    """Teilchenwasser: jede Zelle ist leer, Wasser oder Wand."""

    def __init__(
        self,
        width: int,
        height: int,
        rng: random.Random,
        walls: Framebuffer | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.rng = rng
        self.cells = [bytearray(width) for _ in range(height)]
        self.fall = [bytearray(width) for _ in range(height)]
        self.push = [bytearray(width) for _ in range(height)]
        self.right = [bytearray(width) for _ in range(height)]
        self.stamp = [[0] * width for _ in range(height)]
        self.tick = 0
        self.drains: set[int] = set()
        # Frei fliegende Spritzer: [x, y, vx, vy]
        self.drops: list[list[float]] = []
        self.splash = 0.35
        self.reach = REACH
        if walls is not None:
            for y in range(height):
                for x in range(width):
                    if walls.get(x, y):
                        self.cells[y][x] = WALL

    # -- Zellen ------------------------------------------------------------
    def free(self, x: int, y: int) -> bool:
        if y == self.height:
            return x in self.drains
        if x < 0 or x >= self.width or y < 0 or y > self.height:
            return False
        return self.cells[y][x] == EMPTY

    def add(self, x: int, y: int, fall: int = 0, push: int = 0) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if self.cells[y][x] != EMPTY:
            return False
        self.cells[y][x] = WATER
        self.fall[y][x] = fall
        self.push[y][x] = push
        self.right[y][x] = self.rng.random() < 0.5
        self.stamp[y][x] = self.tick
        return True

    def remove(self, x: int, y: int) -> None:
        if self.cells[y][x] == WATER:
            self.cells[y][x] = EMPTY

    def fill(self, x0: int, y0: int, x1: int, y1: int) -> None:
        for y in range(max(0, y0), min(self.height, y1)):
            for x in range(max(0, x0), min(self.width, x1)):
                self.add(x, y)

    def count(self) -> int:
        return sum(row.count(WATER) for row in self.cells) + len(self.drops)

    def column_top(self, x: int) -> int | None:
        """Oberster Wassertropfen einer Spalte."""
        for y in range(self.height):
            if self.cells[y][x] == WATER:
                return y
        return None

    def _relocate(self, x: int, y: int, nx: int, ny: int) -> None:
        self.cells[y][x] = EMPTY
        if ny >= self.height:
            return  # durch den Abfluss verschwunden
        self.cells[ny][nx] = WATER
        self.fall[ny][nx] = self.fall[y][x]
        self.push[ny][nx] = self.push[y][x]
        self.right[ny][nx] = self.right[y][x]
        self.stamp[ny][nx] = self.tick

    # -- Ablauf ------------------------------------------------------------
    def step(self) -> None:
        self.tick += 1
        self._fly()
        for y in range(self.height - 1, -1, -1):
            row = self.cells[y]
            stamps = self.stamp[y]
            columns = range(self.width)
            if (self.tick + y) % 2:
                columns = range(self.width - 1, -1, -1)
            for x in columns:
                if row[x] == WATER and stamps[x] != self.tick:
                    self._move(x, y)

    def _move(self, x: int, y: int) -> None:
        free = self.free
        direction = 1 if self.right[y][x] else -1

        # Fallen, mit zunehmender Geschwindigkeit.
        speed = min(self.fall[y][x] + 1, MAX_FALL)
        target = y
        while target - y < speed and free(x, target + 1):
            target += 1
        if target > y:
            self.fall[y][x] = target - y
            # Wer faellt, hat Energie, um sich unten noch auszubreiten.
            self.push[y][x] = max(self.push[y][x], FLOW)
            self._relocate(x, y, x, target)
            return

        impact = self.fall[y][x]
        self.fall[y][x] = 0
        if impact >= MAX_FALL and y > 0 and self.rng.random() < self.splash:
            # Harter Aufprall: der Tropfen spritzt wieder hoch.
            self.cells[y][x] = EMPTY
            self.drops.append(
                [
                    float(x),
                    float(y - 1),
                    direction * self.rng.uniform(0.4, 1.3),
                    -self.rng.uniform(0.9, 1.8),
                ]
            )
            return
        if impact >= 2:
            self.push[y][x] = max(self.push[y][x], impact * 2)

        # Schraeg nach unten abrutschen - und dabei Schwung mitnehmen.
        for side in (direction, -direction):
            if free(x + side, y + 1):
                self.right[y][x] = side > 0
                self.fall[y][x] = 1
                self.push[y][x] = max(self.push[y][x], 3)
                self._relocate(x, y, x + side, y + 1)
                return

        # Mit Schwung seitlich weiterfliessen.
        push = self.push[y][x]
        if push:
            for side in (direction, -direction):
                nx = x
                while abs(nx - x) < 2 and free(nx + side, y):
                    nx += side
                if nx != x:
                    self.push[y][x] = push - 1
                    self.right[y][x] = side > 0
                    self._relocate(x, y, nx, y)
                    return
            # Eingekeilt: der Druck bleibt eine Weile, bis vorne Platz wird.
            self.push[y][x] = push - 1
            return

        # Lastet Wasser darauf, drueckt es seitlich in jede Luecke - so
        # schiesst eine Flutwelle flach ueber den Boden.
        if y > 0 and self.cells[y - 1][x] == WATER:
            for side in (direction, -direction):
                nx = x
                while abs(nx - x) < GLIDE and free(nx + side, y):
                    nx += side
                if nx != x:
                    self.right[y][x] = side > 0
                    self._relocate(x, y, nx, y)
                    return

        # Ruhendes Wasser fliesst nur, wenn es nebenan tiefer geht.
        for side in (direction, -direction):
            nx = x
            for _ in range(self.reach):
                if not free(nx + side, y):
                    break
                nx += side
                if free(nx, y + 1):
                    self.right[y][x] = side > 0
                    step = side * min(GLIDE, abs(nx - x))
                    self._relocate(x, y, x + step, y)
                    return

    def _fly(self) -> None:
        """Spritzer fliegen ballistisch, bis sie irgendwo aufschlagen."""
        landed: list[list[float]] = []
        for drop in self.drops:
            drop[3] += GRAVITY
            x, y, vx, vy = drop
            steps = max(1, math.ceil(max(abs(vx), abs(vy))))
            px, py = round(x), round(y)
            for k in range(1, steps + 1):
                cx = round(x + vx * k / steps)
                cy = round(y + vy * k / steps)
                if cx < 0 or cx >= self.width:
                    drop[2] = -vx * 0.5
                    cx = px
                if cy < 0:
                    px, py = cx, cy
                    continue
                if not self.free(cx, cy):
                    landed.append(drop)
                    self._land(px, py, vy)
                    break
                if cy >= self.height:
                    landed.append(drop)  # in den Abfluss gefallen
                    break
                px, py = cx, cy
            else:
                drop[0] = x + vx
                drop[1] = y + vy
        for drop in landed:
            self.drops.remove(drop)

    def _land(self, x: int, y: int, vy: float) -> None:
        x = min(max(x, 0), self.width - 1)
        y = min(y, self.height - 1)
        while y >= 0 and self.cells[y][x] != EMPTY:
            y -= 1
        if y >= 0:
            self.add(x, y, fall=min(MAX_FALL - 1, max(0, int(vy))), push=2)

    # -- Ausgabe -----------------------------------------------------------
    def render(self) -> Framebuffer:
        frame = Framebuffer.from_rows(
            [bytearray(bytes(row).translate(_ON)) for row in self.cells]
        )
        for x, y, _vx, _vy in self.drops:
            frame.set(round(x), round(y), 1)
        return frame


class _Surface:
    """Flachwasser (1D) als Saeulenhoehen plus frei fliegende Tropfen.

    Geloest werden die Flachwassergleichungen mit dem Rusanov-Verfahren:
    robust bei trockenem Boden, und hohe Wellen laufen schneller als flache,
    holen sie ein und steilen sich von selbst zu Brechern auf.
    """

    def __init__(
        self,
        width: int,
        height: int,
        rng: random.Random,
        depth: float = 0.0,
        gravity: float = 0.05,
    ) -> None:
        self.width = width
        self.height = height
        self.rng = rng
        self.level = [depth] * width
        self.momentum = [0.0] * width
        self.gravity = gravity
        self.damping = 0.999
        self.drains: set[int] = set()
        self.drain_rate = 0.4
        # Frei fliegende Tropfen: [x, y, vx, vy], jeder eine Zelle Wasser.
        self.drops: list[list[float]] = []
        self.splash = 0.3
        self.spray = 0.0  # Gischt, wenn Wasser an einer Wand hochschiesst

    # -- Oberflaeche -------------------------------------------------------
    def step(self, accel: float = 0.0) -> None:
        """Einen Zeitschritt rechnen, intern so fein wie noetig (CFL)."""
        remaining = 1.0
        g = self.gravity
        while remaining > 1e-6:
            fastest = 0.05
            for h, m in zip(self.level, self.momentum):
                if h > DRY:
                    fastest = max(fastest, abs(m / h) + math.sqrt(g * h))
            dt = min(remaining, CFL / fastest)
            self._advance(dt, accel)
            remaining -= dt
        for x in self.drains:
            self.level[x] = max(0.0, self.level[x] - self.drain_rate)
        if self.spray:
            self._spray()
        self._fly()

    def _advance(self, dt: float, accel: float) -> None:
        level = self.level
        momentum = self.momentum
        g = self.gravity
        n = self.width
        flux_h = [0.0] * (n + 1)
        flux_m = [0.0] * (n + 1)
        for i in range(n + 1):
            # Waende links und rechts spiegeln die Stroemung.
            if i == 0:
                hl, ml, hr, mr = level[0], -momentum[0], level[0], momentum[0]
            elif i == n:
                hl, ml = level[n - 1], momentum[n - 1]
                hr, mr = hl, -ml
            else:
                hl, ml, hr, mr = level[i - 1], momentum[i - 1], level[i], momentum[i]
            ul = ml / hl if hl > DRY else 0.0
            ur = mr / hr if hr > DRY else 0.0
            speed = max(abs(ul) + math.sqrt(g * hl), abs(ur) + math.sqrt(g * hr))
            flux_h[i] = 0.5 * (hl * ul + hr * ur) - 0.5 * speed * (hr - hl)
            flux_m[i] = (
                0.5 * (hl * ul * ul + 0.5 * g * hl * hl + hr * ur * ur + 0.5 * g * hr * hr)
                - 0.5 * speed * (hr * ur - hl * ul)
            )
        damping = self.damping ** dt
        for i in range(n):
            h = level[i] - dt * (flux_h[i + 1] - flux_h[i])
            m = momentum[i] - dt * (flux_m[i + 1] - flux_m[i])
            if h <= DRY:
                level[i] = max(0.0, h)
                momentum[i] = 0.0
            else:
                level[i] = h
                momentum[i] = (m + dt * h * accel) * damping

    def hump(self, center: float, amount: float, spread: float) -> None:
        for x in range(self.width):
            self.level[x] += amount * math.exp(-(((x - center) / spread) ** 2))

    def take(self, x: int, amount: float = 1.0) -> bool:
        """Wasser an einer Stelle entnehmen (etwa fuer die Pumpe)."""
        if self.level[x] < amount:
            return False
        self.level[x] -= amount
        return True

    def volume(self) -> float:
        return sum(self.level) + len(self.drops)

    def _spray(self) -> None:
        """Wo das Wasser ueber den Rand will, spritzt es als Gischt hoch."""
        for x in range(self.width):
            if self.level[x] > self.height - 0.5 and self.rng.random() < self.spray:
                self.level[x] -= 1
                side = 1 if x < self.width // 2 else -1
                self.throw(x, 0.0, -side * self.rng.uniform(0.2, 1.0),
                           -self.rng.uniform(0.5, 1.5))

    # -- Tropfen -----------------------------------------------------------
    def throw(self, x: float, y: float, vx: float, vy: float) -> None:
        self.drops.append([x, y, vx, vy])

    def _fly(self) -> None:
        surviving = []
        height = self.height
        for drop in self.drops:
            drop[3] += GRAVITY
            drop[0] += drop[2]
            drop[1] += drop[3]
            if drop[0] < 0:
                drop[0], drop[2] = 0.0, -drop[2] * 0.5
            elif drop[0] > self.width - 1:
                drop[0], drop[2] = float(self.width - 1), -drop[2] * 0.5
            x = round(drop[0])
            if drop[3] > 0 and drop[1] >= height - self.level[x] - 0.5:
                self._plunge(x, drop[2], drop[3])
            else:
                surviving.append(drop)
        self.drops = surviving

    def _plunge(self, x: int, vx: float, vy: float) -> None:
        """Ein Tropfen taucht ein: Volumen dazu, Delle, Schwung, Spritzer."""
        level = self.level
        level[x] += 1.0
        dent = min(1.5, 0.35 * vy)
        taken = min(level[x], dent)
        level[x] -= taken
        for side in (-1, 1):
            if 0 <= x + side < self.width:
                level[x + side] += taken / 2
            else:
                level[x] += taken / 2
        self.momentum[x] += 0.3 * vx
        if vy > 1.6 and self.rng.random() < self.splash and level[x] >= 1:
            level[x] -= 1
            side = self.rng.choice((-1, 1))
            self.throw(float(x), self.height - level[x] - 1,
                       side * self.rng.uniform(0.3, 1.1),
                       -self.rng.uniform(0.6, 0.35 * vy + 0.6))

    # -- Ausgabe -----------------------------------------------------------
    def render(self, foam: float = 0.0) -> Framebuffer:
        frame = Framebuffer(self.width, self.height)
        level = self.level
        rng = self.rng
        for x in range(self.width):
            top = self.height - round(level[x])
            if top < self.height:
                frame.vline(x, max(0, top), self.height - max(0, top))
            if foam and 0 < x < self.width - 1 and level[x] >= 1:
                # Gischt auf steilen Wellenkaemmen.
                steep = max(level[x] - level[x - 1], level[x] - level[x + 1])
                if steep > 0.8 and rng.random() < foam * steep:
                    frame.set(x, top - 1 - rng.randrange(2), 1)
        for x, y, vx, vy in self.drops:
            px, py = round(x), round(y)
            frame.set(px, py, 1)
            if vy > 1.2 and abs(vx) < 0.5:
                frame.set(px, py - 1, 1)  # schnelle Tropfen ziehen einen Strich
        return frame


# -- Die Geschichten ---------------------------------------------------------
Scene = Iterator[Framebuffer]


def _until_empty(pool: _Pool, limit: int) -> Scene:
    """Ablaufen lassen; was irgendwo haengen bleibt, faellt am Ende durch."""
    pool.reach = pool.width
    last, still = -1, 0
    for _ in range(limit):
        count = pool.count()
        if not count:
            break
        still = still + 1 if count == last else 0
        last = count
        if still > 24:
            break  # nur noch Wasser, das in einem Hindernis festsitzt
        if still > 12 or count < pool.width * 0.6:
            # Der letzte duenne Rest rinnt ueberall gleichzeitig weg.
            pool.drains.update(range(pool.width))
        pool.step()
        yield pool.render()


def _run(surface: _Surface, steps: int, foam: float = 0.0) -> Scene:
    for _ in range(steps):
        surface.step()
        yield surface.render(foam)


def _drain_away(surface: _Surface, foam: float = 0.0, holes: int = 4) -> Scene:
    """Zum Schluss oeffnen sich Loecher im Boden und alles laeuft ab."""
    spacing = surface.width // holes
    for index in range(holes):
        start = spacing // 2 + index * spacing
        surface.drains.update(range(start - 1, start + 2))
    for _ in range(900):
        if surface.volume() < surface.width * 0.3 and not surface.drops:
            break
        surface.step()
        yield surface.render(foam)
    surface.level = [0.0] * surface.width


def _pour(width: int, height: int, rng: random.Random, _walls: Framebuffer | None) -> Scene:
    """Jemand kippt aus einer Kanne Wasser hinein."""
    surface = _Surface(width, height, rng)
    surface.splash = 0.45
    base = rng.uniform(5, max(6, width / 5))
    if rng.random() < 0.5:
        base = width - 1 - base
    phase = rng.random() * math.tau
    target = width * height * 0.45
    step = 0
    while surface.volume() < target and step < 900:
        # Der Strahl wackelt, als wuerde eine Hand die Kanne halten.
        x = base + 2.5 * math.sin(step / 13 + phase) + 0.7 * math.sin(step / 3.7)
        toward = 0.35 if base < width / 2 else -0.35
        for _ in range(3):
            surface.throw(x + rng.uniform(-0.4, 0.4), -1.0,
                          toward + rng.gauss(0, 0.05), rng.uniform(0.3, 0.6))
        surface.step()
        step += 1
        yield surface.render(foam=0.2)
    yield from _run(surface, 90, foam=0.2)
    yield from _drain_away(surface)


def _dam_break(width: int, height: int, rng: random.Random, _walls: Framebuffer | None) -> Scene:
    """Eine Wassersaeule hinter einem Damm, der ploetzlich bricht."""
    surface = _Surface(width, height, rng)
    surface.spray = 0.25
    dam = int(width * rng.uniform(0.22, 0.3))
    for x in range(dam):
        surface.level[x] = height - 1.5
    held = surface.render()
    held.vline(dam, 0, height)
    for _ in range(5):
        yield held
    yield from _run(surface, 420, foam=0.4)
    yield from _drain_away(surface)


def _fountain(width: int, height: int, rng: random.Random, _walls: Framebuffer | None) -> Scene:
    """Ein Springbrunnen mit Becken - das Wasser laeuft im Kreis."""
    surface = _Surface(width, height, rng, depth=3.5)
    surface.splash = 0.2
    jet = width // 2 + rng.randint(-width // 6, width // 6)
    for step in range(480):
        # Die Pumpe pulsiert, damit die Fontaene lebt.
        power = 2.6 + 0.45 * math.sin(step / 19) + 0.2 * math.sin(step / 5.3)
        if step < 25:
            power *= step / 25
        for _ in range(2):
            if surface.take(jet + rng.randint(-3, 3)):
                surface.throw(jet + rng.uniform(-0.4, 0.4),
                              height - surface.level[jet] - 1,
                              rng.gauss(0, 0.28), -power - rng.uniform(0, 0.3))
        surface.step()
        yield surface.render()
    yield from _run(surface, 40)
    yield from _drain_away(surface)


def _wave(width: int, height: int, rng: random.Random, _walls: Framebuffer | None) -> Scene:
    """Wellen rollen heran, steilen sich auf, klatschen an die Wand."""
    surface = _Surface(width, height, rng, depth=3.0)
    surface.spray = 0.35
    left = rng.random() < 0.5
    origin = 3 if left else width - 4
    surface.hump(origin, 11, 8)
    for step in range(560):
        if step == 190:
            surface.hump(width - 1 - origin, 8, 6)
        if step == 360:
            surface.hump(origin, 9, 6)
        surface.step()
        yield surface.render(foam=0.5)
    yield from _drain_away(surface, foam=0.3)


def _slosh(width: int, height: int, rng: random.Random, _walls: Framebuffer | None) -> Scene:
    """Ein Glas Wasser wird hin und her gekippt."""
    surface = _Surface(width, height, rng, depth=6.0)
    surface.damping = 0.9995
    surface.spray = 0.2
    # Eigenschwingung des Beckens: einmal hin und zurueck.
    period = 2 * width / math.sqrt(surface.gravity * 6.0)
    sign = rng.choice((-1, 1))
    for step in range(int(period * 3.2)):
        ramp = min(1.0, step / period)
        accel = sign * 0.004 * ramp * math.sin(math.tau * step / period)
        if step > period * 2.2:
            accel = 0.0
        surface.step(accel)
        yield surface.render(foam=0.35)
    yield from _drain_away(surface, foam=0.2)


def _rain(width: int, height: int, rng: random.Random, _walls: Framebuffer | None) -> Scene:
    """Regen faellt in eine Pfuetze, die langsam voll laeuft."""
    surface = _Surface(width, height, rng, depth=1.0)
    surface.damping = 0.99
    surface.splash = 0.6
    total = 460
    for step in range(total):
        # Erst ein paar Tropfen, dann ein Schauer, dann laesst es nach.
        intensity = math.sin(math.pi * step / total) ** 2
        showers = 0.25 + 1.4 * intensity
        while showers > 0:
            if rng.random() < showers:
                surface.throw(rng.uniform(0, width - 1), -2.0,
                              rng.gauss(0, 0.05), rng.uniform(0.8, 1.2))
            showers -= 1
        surface.step()
        yield surface.render()
    yield from _run(surface, 25)
    yield from _drain_away(surface, holes=6)


def _drain(width: int, height: int, rng: random.Random, walls: Framebuffer | None) -> Scene:
    """Volle Wanne, jemand zieht den Stoepsel."""
    pool = _Pool(width, height, rng, walls)
    pool.fill(0, 3, width, height)
    for _ in range(6):
        pool.step()
        yield pool.render()
    center = width // 2 + rng.randint(-width // 5, width // 5)
    pool.drains.update(range(center - 2, center + 2))
    yield from _until_empty(pool, 1500)


def _ripple(width: int, height: int, rng: random.Random, _walls: Framebuffer | None) -> Scene:
    """Draufsicht: Tropfen fallen in einen Teich, die Ringe ueberlagern sich."""
    previous = [[0.0] * width for _ in range(height)]
    current = [[0.0] * width for _ in range(height)]
    damping = 0.965
    total = 360
    next_drop = 0
    for step in range(total + 80):
        if next_drop <= step < total:
            cx, cy = rng.randrange(width), rng.randrange(height)
            for dy in (0, 1):
                for dx in (0, 1):
                    if 0 <= cx + dx < width and 0 <= cy + dy < height:
                        current[cy + dy][cx + dx] = -9.0
            next_drop = step + rng.randint(10, 40)
        following = [[0.0] * width for _ in range(height)]
        for y in range(height):
            above = current[y - 1] if y > 0 else None
            below = current[y + 1] if y < height - 1 else None
            row = current[y]
            old = previous[y]
            new = following[y]
            for x in range(width):
                neighbours = (
                    (row[x - 1] if x > 0 else 0.0)
                    + (row[x + 1] if x < width - 1 else 0.0)
                    + (above[x] if above else 0.0)
                    + (below[x] if below else 0.0)
                )
                new[x] = (neighbours / 2 - old[x]) * damping
        previous, current = current, following
        frame = Framebuffer(width, height)
        for y in range(height):
            row = current[y]
            for x in range(width):
                if row[x] > 0.7:
                    frame.set(x, y, 1)
        yield frame


SCENES: dict[str, Callable[..., Scene]] = {
    FLUID_POUR: _pour,
    FLUID_WAVE: _wave,
    FLUID_RAIN: _rain,
    FLUID_DAM_BREAK: _dam_break,
    FLUID_SLOSH: _slosh,
    FLUID_DRAIN: _drain,
    FLUID_FOUNTAIN: _fountain,
    FLUID_RIPPLE: _ripple,
}

# Hier ist ein Schriftzug ein echtes Hindernis, um das das Wasser fliesst.
_OBSTACLE_SCENES = {FLUID_DRAIN}


def resolve(simulation: str, rng: random.Random) -> str:
    """'surprise' in eine echte Simulation aufloesen."""
    if simulation == FLUID_SURPRISE or simulation not in SCENES:
        return rng.choice(list(SCENES))
    return simulation


def fluid_frames(
    simulation: str,
    width: int,
    height: int,
    frames: int,
    seed: int | None = None,
    overlay: Framebuffer | None = None,
) -> tuple[str, list[Framebuffer]]:
    """Eine Simulation rechnen und auf ``frames`` Bilder verdichten.

    ``overlay`` (etwa ein Schriftzug) wird invertiert ueber das Wasser gelegt,
    damit es darin lesbar bleibt - beim Abfluss ist es sogar ein festes
    Hindernis, in dem Wasser haengen bleibt. Es bleibt als letztes Bild
    stehen; ohne ``overlay`` endet jede Simulation mit leerer Tafel.
    """
    rng = random.Random(seed)
    name = resolve(simulation, rng)
    steps = list(SCENES[name](width, height, rng, overlay))
    count = max(2, frames)
    picked: list[Framebuffer] = []
    for index in range(count):
        position = round((index + 1) * len(steps) / count) - 1
        frame = steps[min(len(steps) - 1, max(0, position))]
        if not picked or picked[-1] is not frame:
            picked.append(frame)

    if overlay is not None:
        solid = name in _OBSTACLE_SCENES
        mixed = []
        for frame in picked:
            frame = frame.copy()
            for y in range(height):
                for x in range(width):
                    if overlay.get(x, y):
                        frame.set(x, y, solid or not frame.get(x, y))
            mixed.append(frame)
        picked = mixed

    final = overlay.copy() if overlay is not None else Framebuffer(width, height)
    if picked[-1] != final:
        picked.append(final)
    return name, picked
