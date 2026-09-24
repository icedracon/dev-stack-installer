#!/usr/bin/env python3
"""Entry point: python3 scripts/jh.py <command>. Stdlib only (Python 3.11+)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from jobhunter.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
