# PyInstaller spec for the app bundle (macOS, Apple Silicon, onedir + windowed .app bundle).
# The bundle is named after clipflow.APP_NAME (currently "Vibe-Board"); this file and the
# internal package keep the former name ClipFlow.
# Build with ./packaging/build_macos.sh (which also generates the icon and verifies the result).
# -*- mode: python ; coding: utf-8 -*-

import sys
import tomllib
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is injected by PyInstaller
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

sys.path.insert(0, str(ROOT / "src"))
from clipflow import APP_NAME  # noqa: E402 - single source of the user-visible name

BUNDLE_ID = "local.devidduong.clipflow"  # reverse-DNS; change before any public release
VERSION = PROJECT["version"]  # e.g. 0.1.0.dev0
SHORT_VERSION = ".".join(VERSION.split(".")[:3])  # CFBundleShortVersionString must be X.Y.Z
ICON = ROOT / "build" / "icon" / "ClipFlow.icns"

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[],  # no data files: icons/QSS are generated in code; user data lives outside
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    # Never bundle test/dev tooling. Qt modules are collected only if imported.
    excludes=["tkinter", "pytest", "_pytest", "pytestqt", "ruff", "PyInstaller", "setuptools"],
    noarchive=False,
    optimize=0,
)
# Qt plugins the app never uses. They would pull in QtQuick/QtQml/VirtualKeyboard/QtPdf
# (~25 MB) or TLS/network-information backends (the app makes no network connections).
EXCLUDED_QT = (
    "platforminputcontexts/libqtvirtualkeyboardplugin",
    "imageformats/libqpdf",
    "/tls/",
    "networkinformation/",
    "generic/libqtuiotouchplugin",
    "QtQuick",
    "QtQml",
    "QtVirtualKeyboard",
    "QtPdf",
)


def _keep(entry):
    return not any(token in entry[0] for token in EXCLUDED_QT)


a.binaries = [entry for entry in a.binaries if _keep(entry)]
a.datas = [entry for entry in a.datas if _keep(entry)]

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch="arm64",
    codesign_identity=None,  # ad-hoc signature (local use); see README for distribution
    entitlements_file=None,
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
app = BUNDLE(  # noqa: F821
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ICON) if ICON.exists() else None,
    bundle_identifier=BUNDLE_ID,
    version=SHORT_VERSION,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": SHORT_VERSION,
        "CFBundleVersion": VERSION,
        "LSMinimumSystemVersion": "13.0",
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "NSHighResolutionCapable": True,
        "NSSupportsAutomaticGraphicsSwitching": True,
        "NSHumanReadableCopyright": "Local-only command library. No network access.",
        # Dock icon stays visible until the Dock-icon decision (Phase 4); not LSUIElement.
        "LSUIElement": False,
    },
)
