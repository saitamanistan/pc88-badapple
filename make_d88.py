"""Package a PC-88 IPL binary (ORG $C000) as a bootable 2D D88."""

import argparse
from pathlib import Path
import struct


SECTOR_SIZE = 256
TRACK_COUNT = 80
SECTORS_PER_TRACK = 16
MAX_PAYLOAD_SIZE = 0x3000


def payload_sector_count(payload: bytes) -> int:
    if not 1 <= len(payload) <= MAX_PAYLOAD_SIZE:
        raise ValueError(f"payload must be 1 to {MAX_PAYLOAD_SIZE} bytes")
    return (len(payload) + SECTOR_SIZE - 1) // SECTOR_SIZE


def payload_start_index(track: int, sector: int, sector_count: int) -> int:
    if not 0 <= track < TRACK_COUNT or not 1 <= sector <= SECTORS_PER_TRACK:
        raise ValueError("track must be 0 to 79 and sector must be 1 to 16")
    start = track * SECTORS_PER_TRACK + sector - 1
    if start == 0:
        raise ValueError("track 0, sector 1 is reserved for the IPL")
    if start + sector_count > TRACK_COUNT * SECTORS_PER_TRACK:
        raise ValueError("payload extends past the end of the disk")
    return start


def make_d88(
    ipl: bytes, payload: bytes = b"", *, track: int = 0, sector: int = 2,
    media: bytes = b"", media_track: int = 0,
) -> bytes:
    if not 1 <= len(ipl) <= 256:
        raise ValueError("IPL must be 1 to 256 bytes and linked for address 0xC000")

    header = bytearray(0x2B0)
    header[:11] = b"PC88 BOOT  "
    header[0x1A] = 0x10  # Write protected
    if payload:
        start = payload_start_index(track, sector, payload_sector_count(payload))
        contents = ipl.ljust(start * SECTOR_SIZE, b"\0") + payload
    else:
        contents = ipl
    if media:
        media_count = (len(media) + SECTOR_SIZE - 1) // SECTOR_SIZE
        media_offset = payload_start_index(media_track, 1, media_count) * SECTOR_SIZE
        if media_offset < len(contents):
            raise ValueError("movie data overlaps the boot program")
        contents = contents.ljust(media_offset, b"\0") + media
    disk = bytearray()
    for track_index in range(TRACK_COUNT):
        struct.pack_into("<I", header, 0x20 + 4 * track_index, len(header) + len(disk))
        cylinder, head = divmod(track_index, 2)
        for sector_id in range(1, SECTORS_PER_TRACK + 1):
            disk += struct.pack(
                "<BBBBHBBB5xH", cylinder, head, sector_id, 1, SECTORS_PER_TRACK, 0, 0, 0, SECTOR_SIZE
            )
            offset = (track_index * SECTORS_PER_TRACK + sector_id - 1) * SECTOR_SIZE
            disk += contents[offset:offset + SECTOR_SIZE].ljust(SECTOR_SIZE, b"\0")

    struct.pack_into("<I", header, 0x1C, len(header) + len(disk))
    return header + disk


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    if args.binary.resolve() == args.image.resolve():
        parser.error("input and output must be different files")
    try:
        args.image.write_bytes(make_d88(args.binary.read_bytes()))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
