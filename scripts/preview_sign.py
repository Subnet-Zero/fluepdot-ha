#!/usr/bin/env python3
"""Die Zielanzeige (fluepdot.destination_sign) ohne Home Assistant nachrechnen.

Die Tafel haengt im Heimnetz, die Entwicklung passiert woanders - deshalb
rendert dieses Skript dieselben Bilder wie die Integration und gibt sie als
ASCII aus. Der Block laesst sich unveraendert in die Aktion fluepdot.draw
einsetzen und damit live auf der Tafel gegenpruefen:

    action: fluepdot.draw
    data:
      framebuffer: |-
        <hier einsetzen>

Aufruf:

    python3 scripts/preview_sign.py                      # Beispielgalerie
    python3 scripts/preview_sign.py --line 6 --destination "Bahnhof Altona"
    python3 scripts/preview_sign.py --png vorschau       # zusaetzlich als PNG

Es werden nur fonts.py, framebuffer.py und sign.py geladen - alles reines
Python, keine Home-Assistant-Installation noetig.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
import types

COMPONENT = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "fluepdot"


def _load() -> tuple:
    """fonts/framebuffer/sign laden, ohne custom_components/fluepdot/__init__.py.

    Das Paket-__init__ zieht Home Assistant herein; hier wird deshalb ein
    Ersatzpaket angelegt, damit die relativen Importe (from .const import ...)
    aufgehen, und nur die vier reinen Module eingelesen.
    """
    package = types.ModuleType("_fluepdot_preview")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_fluepdot_preview"] = package

    modules = {}
    for name in ("const", "fonts", "framebuffer", "sign"):
        spec = importlib.util.spec_from_file_location(
            f"_fluepdot_preview.{name}", COMPONENT / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"_fluepdot_preview.{name}"] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules["fonts"], modules["sign"]


FONTS, SIGN = _load()


def to_ascii(buffer) -> str:
    """Framebuffer als X/. ausgeben.

    Punkt statt Leerzeichen: from_ascii wertet nur 'X' aus, alles andere ist
    aus - so bleibt das Bild beim Kopieren lesbar und trotzdem gueltig.
    """
    return "\n".join(
        "".join("X" if buffer.get(x, y) else "." for x in range(buffer.width))
        for y in range(buffer.height)
    )


def show(title: str, buffer, png: pathlib.Path | None = None) -> None:
    print(f"\n### {title}   ({buffer.width}x{buffer.height}, "
          f"{buffer.count_on()} Punkte an)")
    print("+" + "-" * buffer.width + "+")
    for line in to_ascii(buffer).split("\n"):
        print("|" + line + "|")
    print("+" + "-" * buffer.width + "+")
    if png is not None:
        png.write_bytes(buffer.to_png())
        print(f"    -> {png}")


def gallery() -> list[tuple[str, object]]:
    spec = SIGN.SignSpec
    return [
        ("Normalfall - Rahmen, kleine Ueber-Zeile",
         spec(line_number="M29", destination="Hauptbahnhof", via="Rathaus")),
        ("Kasten gefuellt, Nummer ausgestanzt",
         spec(line_number="M29", destination="Hauptbahnhof", via="Rathaus",
              box="filled")),
        ("Ohne Kasten",
         spec(line_number="M29", destination="Hauptbahnhof", via="Rathaus",
              box="none")),
        ("Ohne Zwischenziel - Ziel mittig",
         spec(line_number="6", destination="Bahnhof Altona")),
        ("Ohne Liniennummer",
         spec(destination="Betriebsfahrt", via="kein Einstieg")),
        ("Langes Ziel - Autofit greift",
         spec(line_number="S3", destination="Landungsbruecken",
              via="Reeperbahn und Altona")),
        ("Sehr langes Ziel - wird gekuerzt",
         spec(line_number="N17", destination="Flughafen Terminal Nord Ankunft",
              via="Ohlsdorf, Fuhlsbuettel und Niendorf Nord")),
        ("Laengere Liniennummer - Kasten waechst mit",
         spec(line_number="RB61", destination="Kiel Hbf", via="Neumuenster")),
        ("Absurd lange Liniennummer - weicht auf 3x5 aus",
         spec(line_number="ICE1234", destination="Kiel Hbf", via="Neumuenster")),
    ] + [
        (f"Liniennummer {number!r} - Kastenbreite",
         spec(line_number=number, destination="Zentrum", via="Markt"))
        for number in ("1", "29", "S3", "M29")
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--width", type=int, default=115)
    parser.add_argument("--height", type=int, default=16)
    parser.add_argument("--line", default=None, help="Liniennummer")
    parser.add_argument("--destination", default=None, help="Ziel")
    parser.add_argument("--via", default="", help="Zwischenziel")
    parser.add_argument("--prefix", default=None, help="Vorsatz vor dem Zwischenziel")
    parser.add_argument("--box", default="outline", choices=["outline", "filled", "none"])
    parser.add_argument("--font", default=None, help="Schrift fuer das Ziel")
    parser.add_argument("--scroll", action="store_true", help="Scroll-Frames zeigen")
    parser.add_argument("--png", metavar="VERZEICHNIS", default=None,
                        help="Bilder zusaetzlich als PNG ablegen")
    args = parser.parse_args()

    registry = FONTS.FontRegistry()
    out = pathlib.Path(args.png) if args.png else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    if args.destination or args.line:
        kwargs = {
            "line_number": args.line or "",
            "destination": args.destination or "",
            "via": args.via,
            "box": args.box,
            "font": args.font,
        }
        if args.prefix is not None:
            kwargs["via_prefix"] = args.prefix
        entries = [("Eigene Eingabe", SIGN.SignSpec(**kwargs))]
    else:
        entries = gallery()

    for index, (title, spec) in enumerate(entries):
        buffer = SIGN.render_sign(spec, registry, args.width, args.height)
        show(title, buffer, out / f"{index:02d}.png" if out else None)

    if args.scroll:
        spec = entries[0][1]
        frames = SIGN.sign_frames(spec, registry, args.width, args.height)
        print(f"\n### Scrollen: {len(frames)} Frames")
        for number in (0, len(frames) // 3, 2 * len(frames) // 3, len(frames) - 1):
            show(f"Frame {number + 1}/{len(frames)}", frames[number],
                 out / f"scroll-{number:03d}.png" if out else None)

    print("\nZum Gegenpruefen an der Tafel: Entwicklerwerkzeuge -> Aktionen ->")
    print("YAML-Modus, fluepdot.draw, und den Inhalt zwischen den Rahmen als")
    print("framebuffer einsetzen (die '|'-Randzeichen weglassen).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
