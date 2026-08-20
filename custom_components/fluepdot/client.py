"""HTTP-Client fuer die fluepboard.

Die Firmware kennt keine Authentifizierung und antwortet auf sehr einfache
Endpunkte. Alle Schreibvorgaenge laufen durch einen Lock, damit sich zwei
gleichzeitige Aufrufe nicht gegenseitig ueberschreiben - das Geraet hat nur
einen Framebuffer.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from .const import DEFAULT_TIMEOUT, FIXED_HEIGHT

_LOGGER = logging.getLogger(__name__)


class FluepdotError(Exception):
    """Fehler bei der Kommunikation mit der Anzeige."""


class FluepdotClient:
    """Schlanker Wrapper um die HTTP-API der fluepboard."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._session = session
        self._host = host.rstrip("/")
        if not self._host.startswith(("http://", "https://")):
            self._host = f"http://{self._host}"
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lock = asyncio.Lock()

    @property
    def host(self) -> str:
        return self._host

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: bytes | None = None,
    ) -> str:
        url = f"{self._host}{path}"
        try:
            async with self._session.request(
                method,
                url,
                params=params,
                data=data,
                timeout=self._timeout,
                headers={"Content-Type": "text/plain"} if data else None,
            ) as response:
                body = await response.text()
                if response.status >= 400:
                    raise FluepdotError(
                        f"{method} {path} lieferte HTTP {response.status}"
                    )
                return body
        except TimeoutError as err:
            raise FluepdotError(f"{method} {path}: Zeitueberschreitung") from err
        except aiohttp.ClientError as err:
            raise FluepdotError(f"{method} {path}: {err}") from err

    # -- Framebuffer -------------------------------------------------------
    async def get_framebuffer(self) -> str:
        """Aktuellen Framebuffer als ASCII lesen."""
        return await self._request("GET", "/framebuffer")

    async def post_framebuffer(self, ascii_data: str) -> None:
        """Kompletten Framebuffer schreiben."""
        async with self._lock:
            await self._request(
                "POST", "/framebuffer", data=ascii_data.encode("utf-8")
            )

    async def post_text(
        self,
        text: str,
        font: str | None = None,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Text vom Geraet selbst rendern lassen."""
        params: dict[str, str] = {}
        if font:
            params["font"] = font
        if x is not None:
            params["x"] = str(x)
        if y is not None:
            params["y"] = str(y)
        async with self._lock:
            await self._request(
                "POST", "/framebuffer/text", params=params, data=text.encode("utf-8")
            )

    async def clear(self, width: int, height: int = FIXED_HEIGHT) -> None:
        """Anzeige leeren (die Firmware hat dafuer keinen eigenen Endpunkt)."""
        blank = ((" " * width) + "\n") * height
        await self.post_framebuffer(blank)

    # -- Einzelne Punkte ---------------------------------------------------
    # Achtung: Diese beiden Endpunkte quittieren mit HTTP 200 und GET /pixel
    # meldet danach den neuen Wert, die Tafel zeichnet ihn aber nicht (am
    # 2026-08-20 am Geraet nachgemessen). Die Aktionen fluepdot.set_pixel und
    # fluepdot.clear_pixel gehen deshalb ueber den Framebuffer. Hier bleiben
    # sie nur der Vollstaendigkeit halber stehen.
    async def set_pixel(self, x: int, y: int) -> None:
        async with self._lock:
            await self._request(
                "POST", "/pixel", params={"x": str(x), "y": str(y)}
            )

    async def clear_pixel(self, x: int, y: int) -> None:
        async with self._lock:
            await self._request(
                "DELETE", "/pixel", params={"x": str(x), "y": str(y)}
            )

    # -- Schriften ---------------------------------------------------------
    async def get_fonts(self) -> list[tuple[str, str]]:
        """Installierte Schriften lesen: je zwei Zeilen (Langname, Kurzname)."""
        body = await self._request("GET", "/fonts")
        lines = [line.strip() for line in body.split("\n") if line.strip()]
        fonts: list[tuple[str, str]] = []
        for index in range(0, len(lines) - 1, 2):
            fonts.append((lines[index], lines[index + 1]))
        return fonts

    # -- Rendering ---------------------------------------------------------
    async def get_rendering_mode(self) -> int:
        body = await self._request("GET", "/rendering/mode")
        try:
            return int(body.strip().split()[0])
        except (ValueError, IndexError):
            return 0

    async def set_rendering_mode(self, mode: int) -> None:
        async with self._lock:
            await self._request(
                "PUT", "/rendering/mode", data=str(int(mode)).encode("ascii")
            )

    async def get_timings(self) -> list[tuple[int, int, int]]:
        """Timings je Spalte lesen: (pre, clear, set) in 50-us-Schritten."""
        body = await self._request("GET", "/rendering/timings")
        values = [line.strip() for line in body.split("\n") if line.strip()]
        timings: list[tuple[int, int, int]] = []
        for index in range(0, len(values) - 2, 3):
            try:
                timings.append(
                    (
                        int(values[index]),
                        int(values[index + 1]),
                        int(values[index + 2]),
                    )
                )
            except ValueError:
                continue
        return timings

    async def set_timings(self, timings: list[tuple[int, int, int]]) -> None:
        payload = "".join(
            f"{pre:05d}\n{clear:05d}\n{set_:05d}\n" for pre, clear, set_ in timings
        )
        async with self._lock:
            await self._request(
                "POST", "/rendering/timings", data=payload.encode("ascii")
            )

    # -- Diagnose ----------------------------------------------------------
    async def probe(self) -> tuple[int, int]:
        """Geometrie ermitteln: (Breite, Hoehe) aus dem Framebuffer."""
        body = await self.get_framebuffer()
        lines = body.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if not lines:
            raise FluepdotError("Anzeige lieferte einen leeren Framebuffer")
        width = max(len(line) for line in lines)
        return width, len(lines)
