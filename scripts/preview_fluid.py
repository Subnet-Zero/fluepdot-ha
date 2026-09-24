#!/usr/bin/env python3
"""Die Fluessigkeits-Simulationen (fluepdot.fluid) ohne Home Assistant ansehen.

Spielt eine Simulation als ASCII-Animation im Terminal ab und schreibt auf
Wunsch ein animiertes GIF im Flipdot-Look - so laesst sich eine Aenderung
beurteilen, bevor die echte Tafel dafuer klappern muss.

Aufruf:

    python3 scripts/preview_fluid.py                     # alle nacheinander
    python3 scripts/preview_fluid.py --sim pour
    python3 scripts/preview_fluid.py --sim dam_break --text "HALLO"
    python3 scripts/preview_fluid.py --gif vorschau      # vorschau/<sim>.gif
    python3 scripts/preview_fluid.py --gif vorschau --no-play

Geladen werden nur const, fonts, framebuffer und fluid - reines Python.
"""

from __future__ import annotations

import argparse
import importlib.util
import pathlib
import sys
import time
import types

COMPONENT = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "fluepdot"


def _load() -> dict:
    """Die reinen Module laden, ohne das Paket-__init__ (das zieht HA herein)."""
    package = types.ModuleType("_fluepdot_preview")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_fluepdot_preview"] = package
    modules = {}
    for name in ("const", "fonts", "framebuffer", "fluid"):
        spec = importlib.util.spec_from_file_location(
            f"_fluepdot_preview.{name}", COMPONENT / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"_fluepdot_preview.{name}"] = module
        spec.loader.exec_module(module)
        modules[name] = module
    return modules


MODULES = _load()
CONST = MODULES["const"]
FONTS = MODULES["fonts"]
FRAMEBUFFER = MODULES["framebuffer"]
FLUID = MODULES["fluid"]


def text_overlay(text: str, width: int, height: int):
    registry = FONTS.FontRegistry()
    font = registry.get(FONTS.BUILTIN_FONT_NAME)
    buffer = FRAMEBUFFER.Framebuffer(width, height)
    buffer.draw_lines(font, [text], align=CONST.ALIGN_CENTER, valign=CONST.VALIGN_MIDDLE)
    return buffer


def play(frames, delay: float) -> None:
    width = frames[0].width
    border = "+" + "-" * width + "+"
    sys.stdout.write("\x1b[2J")
    for index, frame in enumerate(frames):
        lines = [border]
        for y in range(frame.height):
            lines.append(
                "|" + "".join("#" if frame.get(x, y) else " " for x in range(width)) + "|"
            )
        lines.append(border)
        lines.append(f"Bild {index + 1}/{len(frames)}")
        sys.stdout.write("\x1b[H" + "\n".join(lines) + "\n")
        sys.stdout.flush()
        time.sleep(delay)


# -- Minimaler GIF-Schreiber -------------------------------------------------
# Palette: 0 = Gehaeuse, 1 = Punkt aus (dunkel), 2 = Punkt an (gelb).
PALETTE = bytes((20, 20, 20, 40, 40, 40, 255, 214, 0, 0, 0, 0))


def _lzw(pixels: bytes, min_size: int = 2) -> bytes:
    clear = 1 << min_size
    end = clear + 1
    size = min_size + 1
    table = {bytes([i]): i for i in range(clear)}
    next_code = end + 1
    out = bytearray()
    bits = 0
    count = 0

    def emit(code: int) -> None:
        nonlocal bits, count
        bits |= code << count
        count += size
        while count >= 8:
            out.append(bits & 0xFF)
            bits >>= 8
            count -= 8

    emit(clear)
    word = b""
    for value in pixels:
        char = bytes([value])
        joined = word + char
        if joined in table:
            word = joined
            continue
        emit(table[word])
        if next_code < 4096:
            table[joined] = next_code
            next_code += 1
            if next_code > (1 << size) and size < 12:
                size += 1
        else:
            emit(clear)
            table = {bytes([i]): i for i in range(clear)}
            next_code = end + 1
            size = min_size + 1
        word = char
    if word:
        emit(table[word])
    emit(end)
    if count:
        out.append(bits & 0xFF)
    return bytes(out)


def write_gif(path: pathlib.Path, frames, delay: float, scale: int = 5) -> None:
    width = frames[0].width * scale
    height = frames[0].height * scale
    data = bytearray(b"GIF89a")
    data += width.to_bytes(2, "little") + height.to_bytes(2, "little")
    data += bytes((0xF1, 0, 0)) + PALETTE
    data += b"\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00"  # Endlosschleife
    centisec = max(2, round(delay * 100))
    for frame in frames:
        pixels = bytearray()
        for y in range(frame.height):
            row = bytearray()
            for x in range(frame.width):
                color = 2 if frame.get(x, y) else 1
                row += bytes([color] * (scale - 1)) + b"\x00"
            for _ in range(scale - 1):
                pixels += row
            pixels += bytes(width)
        data += b"\x21\xf9\x04\x00" + centisec.to_bytes(2, "little") + b"\x00\x00"
        data += b"\x2c\x00\x00\x00\x00"
        data += width.to_bytes(2, "little") + height.to_bytes(2, "little") + b"\x00"
        data += b"\x02"
        packed = _lzw(bytes(pixels))
        for start in range(0, len(packed), 255):
            chunk = packed[start : start + 255]
            data += bytes([len(chunk)]) + chunk
        data += b"\x00"
    data += b"\x3b"
    path.write_bytes(bytes(data))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sim", choices=CONST.FLUID_SIMULATIONS, action="append")
    parser.add_argument("--duration", type=float, default=CONST.DEFAULT_FLUID_DURATION)
    parser.add_argument("--delay", type=float, default=CONST.DEFAULT_FLUID_DELAY)
    parser.add_argument("--width", type=int, default=CONST.DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=CONST.FIXED_HEIGHT)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--text", help="Schriftzug als Hindernis")
    parser.add_argument("--gif", type=pathlib.Path, help="Ordner fuer animierte GIFs")
    parser.add_argument("--no-play", action="store_true")
    args = parser.parse_args()

    overlay = text_overlay(args.text, args.width, args.height) if args.text else None
    frames_wanted = min(CONST.MAX_FLUID_FRAMES, max(2, round(args.duration / args.delay)))
    for simulation in args.sim or [s for s in CONST.FLUID_SIMULATIONS if s != "surprise"]:
        started = time.perf_counter()
        name, frames = FLUID.fluid_frames(
            simulation, args.width, args.height, frames_wanted, args.seed, overlay
        )
        took = time.perf_counter() - started
        print(f"{name}: {len(frames)} Bilder in {took:.2f} s gerechnet")
        if args.gif:
            args.gif.mkdir(parents=True, exist_ok=True)
            target = args.gif / f"{name}.gif"
            write_gif(target, frames, args.delay)
            print(f"    -> {target}")
        if not args.no_play:
            play(frames, args.delay)


if __name__ == "__main__":
    main()
