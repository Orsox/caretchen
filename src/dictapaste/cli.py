from __future__ import annotations

import sys

from .main import main


def cli() -> int:
    return main()


if __name__ == "__main__":
    raise SystemExit(cli())
