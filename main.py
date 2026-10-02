"""Vibe-Board entry point: ``python main.py``."""

import sys
from pathlib import Path

# Allow running from a checkout even if the package was not installed with ``pip install -e .``.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from clipflow.app import main

if __name__ == "__main__":
    sys.exit(main())
