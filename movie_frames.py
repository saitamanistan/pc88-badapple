"""Generate a looping white-on-black test animation in PC-88 semigraphics."""

import argparse
from math import cos, pi, sin
from pathlib import Path
from struct import pack

WIDTH = 64
HEIGHT = 64
FRAME_SIZE = WIDTH * HEIGHT // 8
DEMO_FRAMES = 48
FULL_FRAME = 0xFF


def encode_movie(frames: bytes, *, notes: bytes = b"", notes_per_frame: int = 0) -> bytes:
    """Encode full frames or runs of changed cells, whichever takes fewer bytes."""
    if not frames or len(frames) % FRAME_SIZE:
        raise ValueError(f"movie data must contain complete {FRAME_SIZE}-byte frames")

    previous = frames[:FRAME_SIZE]
    encoded = bytearray(notes[:notes_per_frame])
    encoded.append(FULL_FRAME)
    encoded.extend(previous)
    for offset in range(FRAME_SIZE, len(frames), FRAME_SIZE):
        frame = frames[offset:offset + FRAME_SIZE]
        note_offset = offset // FRAME_SIZE * notes_per_frame
        encoded.extend(notes[note_offset:note_offset + notes_per_frame])
        changes = [index for index, (old, new) in enumerate(zip(previous, frame)) if old != new]
        runs = bytearray()
        count = 0
        cursor = 0
        while cursor < len(changes):
            start = end = changes[cursor]
            cursor += 1
            # A run header costs three bytes. Bridging a small gap is cheaper.
            while (
                cursor < len(changes)
                and changes[cursor] - end <= 4
                and changes[cursor] - start < 255
            ):
                end = changes[cursor]
                cursor += 1
            runs.extend(pack("<HB", start, end - start + 1))
            runs.extend(frame[start:end + 1])
            count += 1
        if len(runs) < FRAME_SIZE:
            encoded.append(count)
            encoded.extend(runs)
        else:
            encoded.append(FULL_FRAME)
            encoded.extend(frame)
        previous = frame
    return bytes(encoded)


def encode_frame(pixels: bytes) -> bytes:
    """Pack one 64x64 grayscale frame into 32x16 PC-88 character cells."""
    if len(pixels) != WIDTH * HEIGHT:
        raise ValueError("a frame must contain 64x64 grayscale pixels")
    return bytes(
        sum(
            (pixels[(y + dy) * WIDTH + x + dx] >= 128) << (dy + dx * 4)
            for dx in range(2)
            for dy in range(4)
        )
        for y in range(0, HEIGHT, 4)
        for x in range(0, WIDTH, 2)
    )


def demo_movie() -> bytes:
    frames = bytearray()
    for frame in range(DEMO_FRAMES):
        angle = 2 * pi * frame / DEMO_FRAMES
        moon_x = 31.5 + 23 * cos(angle)
        moon_y = 31.5 + 19 * sin(angle)
        pixels = bytearray(WIDTH * HEIGHT)
        for y in range(HEIGHT):
            for x in range(WIDTH):
                radius = (x - 31.5) ** 2 + (y - 31.5) ** 2
                orbit = ((x - 31.5) / 23) ** 2 + ((y - 31.5) / 19) ** 2
                moon = (x - moon_x) ** 2 + (y - moon_y) ** 2
                if radius <= 11 ** 2 or 0.94 <= orbit <= 1.06 or moon <= 4 ** 2:
                    pixels[y * WIDTH + x] = 255
        frames.extend(encode_frame(pixels))
    return bytes(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack 64x64 raw grayscale video frames.")
    parser.add_argument("input", type=Path, help="raw 8-bit grayscale frames, without a header")
    parser.add_argument("output", type=Path, help="packed PC-88 semigraphics frames")
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output must be different files")
    frames = args.input.read_bytes()
    pixels_per_frame = WIDTH * HEIGHT
    if not frames or len(frames) % pixels_per_frame:
        parser.error("input must contain complete 64x64 grayscale frames")
    args.output.write_bytes(
        b"".join(
            encode_frame(frames[offset:offset + pixels_per_frame])
            for offset in range(0, len(frames), pixels_per_frame)
        )
    )


if __name__ == "__main__":
    main()
