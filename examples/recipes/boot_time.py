"""Measure a dedicated AVD's cold startup to sys.boot_completed, then stop it."""

import argparse
import time

from geppetto.core import emulator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("avd", help="Name of a dedicated, stopped AVD")
    parser.add_argument("--gpu", choices=("auto", "host", "swiftshader"), default="auto")
    args = parser.parse_args()
    started = time.monotonic()
    serial = emulator.start(
        args.avd,
        headless=True,
        extra_args=["-gpu", args.gpu, "-no-snapshot-load", "-no-snapshot-save"],
        timeout=180,
    )
    try:
        print(f"{serial}: sys.boot_completed after {time.monotonic() - started:.2f}s")
    finally:
        emulator.stop(serial)


if __name__ == "__main__":
    main()
