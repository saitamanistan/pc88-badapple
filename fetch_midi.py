"""Download the referenced Bad Apple!! MIDI arrangement and verify its SHA-256."""

import argparse
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen


URL = "https://raw.githubusercontent.com/rkk-2s/bad-apple/master/alstroemeria_records_bad_apple.mid"
SHA256 = "b0bc6648604bee2b1ea3c17f8f730e1886df9559f35f2b271ba5564da987ad08"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "alstroemeria_records_bad_apple.mid"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="destination MIDI path")
    parser.add_argument("--force", action="store_true", help="re-download even if the file exists")
    args = parser.parse_args()

    if args.output.is_file() and not args.force:
        if sha256(args.output.read_bytes()).hexdigest() == SHA256:
            print(f"Already exists and verified: {args.output}")
            return

    print(f"Downloading {URL} ...", flush=True)
    with urlopen(URL, timeout=60) as response:
        data = response.read()
    if sha256(data).hexdigest() != SHA256:
        raise RuntimeError("Downloaded MIDI SHA-256 did not match")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"Saved {args.output} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
