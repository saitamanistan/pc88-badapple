"""Build a PC-88 boot disk for the Bad Apple!! movie player or a raw Z80 binary."""

import argparse
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import subprocess
from urllib.request import urlopen
from zipfile import ZipFile

from make_d88 import MAX_PAYLOAD_SIZE, SECTOR_SIZE, make_d88, payload_sector_count, payload_start_index
from movie_frames import FRAME_SIZE, demo_movie, encode_movie
from movie_music import CHANNELS, TICKS_PER_FRAME, pitch_table


ROOT = Path(__file__).resolve().parent
TOOLS = ROOT / ".tools"
RELEASE = "sjasmplus-1.24.0.win"
URL = f"https://github.com/z00m128/sjasmplus/releases/download/v1.24.0/{RELEASE}.zip"
SHA256 = "7e1f8840842039bdb97e51a59abda2e5c25a9da160097e8f79a62583ab72d0e0"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--payload", type=Path, help="raw Z80 binary linked at 0x9000")
    inputs.add_argument("--movie", action="store_true", help="build the silent animation demo")
    inputs.add_argument("--movie-data", type=Path, help="packed 64x64 semigraphics frames")
    parser.add_argument("--fm-data", type=Path, help="YM2203 note data produced by movie_music.py")
    parser.add_argument("--output", type=Path, help="output D88 path")
    parser.add_argument("--track", type=int, default=0, help="first payload track (0-79, default 0)")
    parser.add_argument("--sector", type=int, default=2, help="first payload sector (1-16, default 2)")
    parser.add_argument("--sectors", type=int, help="number to load (up to 48, default: payload size)")
    args = parser.parse_args()
    if args.payload is None and not args.movie and args.movie_data is None:
        args.movie_data = ROOT / ".media" / "bad-apple.frames.bin"
        if args.fm_data is None:
            args.fm_data = ROOT / ".media" / "bad-apple.fm.bin"
        if args.output is None:
            args.output = ROOT / "build" / "bad-apple-fm.d88"
    movie = args.movie or args.movie_data is not None
    media = b""
    if args.movie_data is not None:
        try:
            media = args.movie_data.read_bytes()
        except OSError as error:
            parser.error(str(error))
    elif args.movie:
        media = demo_movie()
    if movie and (not media or len(media) % FRAME_SIZE):
        parser.error(f"movie data must contain complete {FRAME_SIZE}-byte frames")
    frame_count = len(media) // FRAME_SIZE
    if frame_count > 0xFFFF:
        parser.error("movie cannot exceed 65535 frames")
    packed_media = encode_movie(media) if movie else b""
    if args.fm_data is not None:
        if not movie:
            parser.error("--fm-data requires --movie or --movie-data")
        try:
            notes = args.fm_data.read_bytes()
        except OSError as error:
            parser.error(str(error))
        notes_per_frame = CHANNELS * TICKS_PER_FRAME
        if len(notes) != frame_count * notes_per_frame:
            parser.error(f"FM data must contain {notes_per_frame} note/percussion bytes per frame")
        packed_media = encode_movie(media, notes=notes, notes_per_frame=notes_per_frame)
    media_track = 4
    payload = args.payload.read_bytes() if args.payload else None
    if payload is not None:
        payload_sector_count(payload)

    assembler = TOOLS / RELEASE / "sjasmplus.exe"
    if not assembler.is_file():
        print("Downloading sjasmplus 1.24.0 ...", flush=True)
        with urlopen(URL, timeout=60) as response:
            archive = response.read()
        if sha256(archive).hexdigest() != SHA256:
            raise RuntimeError("sjasmplus archive SHA-256 did not match")
        with ZipFile(BytesIO(archive)) as zip_file:
            zip_file.extractall(TOOLS)

    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    source = "movie"
    image = args.output.resolve() if args.output is not None else build / ("movie.d88" if movie else "program.d88")
    binary = build / f"{image.stem}.bin"
    ipl = build / (f"{image.stem}.ipl.bin" if args.output is not None else "ipl.bin")
    if payload is None:
        defines = [
            f"-DMOVIE_TRACK={media_track}", f"-DMOVIE_FRAMES={frame_count}",
            f"-DMOVIE_FM={int(args.fm_data is not None)}",
        ] if movie else []
        if args.fm_data is not None:
            (build / "fm_pitch.bin").write_bytes(pitch_table())
        subprocess.run(
            [str(assembler), *defines, f"--raw=build/{binary.name}", f"{source}.asm"],
            cwd=ROOT,
            check=True,
        )
        payload = binary.read_bytes()
    try:
        required = payload_sector_count(payload)
        sectors = required if args.sectors is None else args.sectors
        maximum = MAX_PAYLOAD_SIZE // SECTOR_SIZE
        if not required <= sectors <= maximum:
            raise ValueError(f"load length must be {required} to {maximum} sectors for this payload")
        start = payload_start_index(args.track, args.sector, sectors)
        if movie:
            media_sectors = (len(packed_media) + SECTOR_SIZE - 1) // SECTOR_SIZE
            media_start = payload_start_index(media_track, 1, media_sectors)
            if start + sectors > media_start:
                raise ValueError("the IPL load range overlaps movie data on track 4 or later")
    except ValueError as error:
        parser.error(str(error))
    subprocess.run(
        [
            str(assembler),
            f"-DPAYLOAD_SECTORS={sectors}",
            f"-DPAYLOAD_TRACK={args.track}",
            f"-DPAYLOAD_FIRST_SECTOR={args.sector}",
            f"--raw=build/{ipl.name}",
            "ipl.asm",
        ],
        cwd=ROOT,
        check=True,
    )
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(
        make_d88(
            ipl.read_bytes(), payload, track=args.track, sector=args.sector,
            media=packed_media, media_track=media_track,
        )
    )
    if movie:
        (build / f"{image.stem}.frames.bin").write_bytes(media)
        (build / f"{image.stem}.delta.bin").write_bytes(packed_media)
        print(f"Movie data: {len(media)} -> {len(packed_media)} bytes")
    print(image)


if __name__ == "__main__":
    main()
