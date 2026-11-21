"""Boot the built D88 in an isolated copy of M88gn."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parent


def _default_m88() -> Path | None:
    if os.environ.get("M88_PATH"):
        return Path(os.environ["M88_PATH"])
    env_file = ROOT / ".env.local"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("M88_PATH="):
                value = line.split("=", 1)[1].strip().strip('"')
                if value:
                    return Path(value)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--m88",
        type=Path,
        default=_default_m88(),
        help="path to M88.exe (or set M88_PATH in env or .env.local)",
    )
    parser.add_argument("--image", type=Path, default=ROOT / "build" / "bad-apple-fm.d88")
    args = parser.parse_args()

    try:
        if args.m88 is None:
            raise FileNotFoundError("Specify M88.exe with --m88 or the M88_PATH environment variable.")
        if not args.m88.is_file():
            raise FileNotFoundError(f"M88.exe not found: {args.m88}")
        if not args.image.is_file():
            raise FileNotFoundError(f"D88 not found: {args.image}. Run build.py first.")

        tools = ROOT / ".tools"
        tools.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix="m88-run-", dir=tools) as directory:
            session = Path(directory)
            emulator = session / "M88.exe"
            shutil.copyfile(args.m88, emulator)
            for rom in args.m88.parent.glob("*"):
                if rom.suffix.lower() == ".rom" and rom.is_file():
                    shutil.copyfile(rom, session / rom.name)
            if not (session / "disk.rom").is_file() or not any(
                (session / name).is_file() for name in ("n88.rom", "pc88.rom")
            ):
                raise FileNotFoundError(f"Required PC-88 ROM files not found in {args.m88.parent}")
            shutil.copyfile(args.image, session / "boot.d88")
            print(f"Booting {args.image} in M88gn. Close M88gn to finish.", flush=True)
            subprocess.run(
                [str(emulator), "-b21", "boot.d88"],
                cwd=session,
                check=True,
            )
    except (OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
