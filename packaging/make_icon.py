"""Generate the app icon (ClipFlow.icns, an internal file name) from the painted placeholder
(clipflow.ui.icons.app_icon_pixmap).

    python packaging/make_icon.py build/icon      # writes build/icon/ClipFlow.icns

Deterministic: same code + Qt version gives the same artwork. Replace the artwork in
``app_icon_pixmap`` (or drop a designed ClipFlow.icns into packaging/) for a final icon.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from clipflow.ui.icons import app_icon_pixmap  # noqa: E402

# (iconset file name, pixel size) as required by iconutil.
ICONSET = [
    (f"icon_{points}x{points}{suffix}.png", points * scale)
    for points in (16, 32, 128, 256, 512)
    for suffix, scale in (("", 1), ("@2x", 2))
]


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build" / "icon").resolve()
    designed = ROOT / "packaging" / "ClipFlow.icns"
    out.mkdir(parents=True, exist_ok=True)
    target = out / "ClipFlow.icns"
    if designed.exists():  # a hand-made icon always wins over the placeholder
        shutil.copyfile(designed, target)
        print(f"Using designed icon {designed}")
        return 0
    _app = QGuiApplication(sys.argv[:1])
    iconset = out / "ClipFlow.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir()
    for name, pixels in ICONSET:
        if not app_icon_pixmap(pixels).save(str(iconset / name), "PNG"):
            print(f"Could not write {name}", file=sys.stderr)
            return 1
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(target)], check=True)
    print(f"Wrote placeholder icon {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
