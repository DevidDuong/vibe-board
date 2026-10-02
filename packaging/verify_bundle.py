"""Verify a built app bundle: identity, architecture, signature, and that no user data,
logs, credentials, or dev/test files were packaged.

    python packaging/verify_bundle.py dist/Vibe-Board.app
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from clipflow import APP_NAME

EXPECTED_BUNDLE_ID = "local.devidduong.clipflow"

# Anything matching these must never be inside the bundle.
FORBIDDEN_PATTERNS = (
    "*.sqlite",
    "*.sqlite3",
    "*.sqlite3-*",
    "*.db",
    "*.db-*",
    "*.log",
    ".env",
    ".env.*",
    "id_rsa*",
    "id_ed25519*",
    "*.pem",
    "*.p12",
    "*.key",
    "*.netrc",
    "*.zsh_history",
    "*.bash_history",
    "conftest.py",
    "fakes.py",
    "test_*.py",
    "manual_macos_checklist.md",
)
FORBIDDEN_DIRS = ("tests", ".clipflow-dev-data", "ui-review", "pytest", "_pytest", "pytestqt")


def forbidden_files(bundle: Path) -> list[Path]:
    def forbidden(path: Path) -> bool:
        if path.is_dir():
            return path.name in FORBIDDEN_DIRS
        return path.is_file() and any(fnmatch(path.name, p) for p in FORBIDDEN_PATTERNS)

    return [path for path in bundle.rglob("*") if forbidden(path)]


REQUIRED_MODULES = (
    "clipflow.platform.macos_hotkey",  # global shortcut (Carbon adapter)
    "clipflow.services.hotkey_manager",
    "clipflow.models.hotkey",
    "clipflow.ui.hotkey_edit",
    "clipflow.ui.placement",
    "clipflow.repositories.window_state_repository",
    "clipflow.selftest",
)


def packaged_modules(executable: Path) -> set[str]:
    """Python modules inside the bundle's embedded PYZ archive (PyInstaller's own reader)."""
    from PyInstaller.archive.readers import CArchiveReader

    package = CArchiveReader(str(executable))
    names = [name for name, entry in package.toc.items() if entry[-1] == "z"]
    return set(package.open_embedded_archive(names[0]).toc) if names else set()


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def main() -> int:
    bundle = Path(sys.argv[1] if len(sys.argv) > 1 else f"dist/{APP_NAME}.app").resolve()
    failures: list[str] = []

    def check(ok: bool, label: str, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {label}{f' — {detail}' if detail else ''}")
        if not ok:
            failures.append(label)

    check(bundle.is_dir() and bundle.suffix == ".app", "bundle exists", str(bundle))
    if failures:
        return 1
    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    check(
        info.get("CFBundleIdentifier") == EXPECTED_BUNDLE_ID,
        "bundle identifier",
        str(info.get("CFBundleIdentifier")),
    )
    check(info.get("CFBundleName") == APP_NAME, "bundle name", str(info.get("CFBundleName")))
    check(info.get("CFBundleDisplayName") == APP_NAME, "display name")
    check(info.get("CFBundlePackageType") == "APPL", "package type APPL")
    check(info.get("NSHighResolutionCapable") is True, "high-resolution capable")
    check(
        "SMPrivilegedExecutables" not in info and "SMLoginItem" not in str(info),
        "no login-item registration",
    )
    check(not any(k.endswith("UsageDescription") for k in info), "no privacy permission requests")
    icon = info.get("CFBundleIconFile")
    check(bool(icon) and (bundle / "Contents" / "Resources" / icon).exists(), "app icon", str(icon))

    executable = bundle / "Contents" / "MacOS" / info["CFBundleExecutable"]
    archs = _run("lipo", "-archs", str(executable)).stdout.split()
    check(archs == ["arm64"], "main executable is arm64", " ".join(archs))
    non_arm = []
    for lib in bundle.rglob("*"):
        if lib.suffix in (".so", ".dylib") and lib.is_file() and not lib.is_symlink():
            lib_archs = _run("lipo", "-archs", str(lib)).stdout.split()
            if lib_archs and "arm64" not in lib_archs:
                non_arm.append(lib.name)
    check(not non_arm, "all native libraries contain arm64", ", ".join(non_arm[:5]))
    missing = [m for m in REQUIRED_MODULES if m not in packaged_modules(executable)]
    check(not missing, "global-shortcut and placement code packaged", ", ".join(missing))
    cocoa = list(bundle.rglob("libqcocoa.dylib"))
    check(bool(cocoa), "Qt cocoa platform plugin bundled")

    signature = _run("codesign", "--verify", "--deep", "--strict", str(bundle))
    check(signature.returncode == 0, "code signature valid (ad-hoc)", signature.stderr.strip())
    details = _run("codesign", "-dv", str(bundle)).stderr
    check("Signature=adhoc" in details, "signed ad-hoc (not Developer ID)")

    hits = forbidden_files(bundle)
    check(
        not hits,
        "no user data, logs, credentials or test files packaged",
        ", ".join(str(h.relative_to(bundle)) for h in hits[:5]),
    )

    unused = [
        p.name
        for p in bundle.rglob("*")
        if any(t in p.name for t in ("virtualkeyboard", "libqpdf", "QtQuick", "QtQml", "QtPdf"))
    ]
    unused += [p.name for p in bundle.rglob("tls") if p.is_dir()]
    check(not unused, "unused Qt plugins/frameworks excluded", ", ".join(unused[:5]))

    files = [p for p in bundle.rglob("*") if p.is_file() and not p.is_symlink()]
    size_mb = sum(p.stat().st_size for p in files) / 1_048_576
    print(f"INFO  bundle size {size_mb:.0f} MB")
    print("OK" if not failures else f"FAILED: {', '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
