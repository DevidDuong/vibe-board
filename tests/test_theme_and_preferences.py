from __future__ import annotations

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

from clipflow.models.preferences import UiPreferences
from clipflow.repositories.preferences_repository import KEYS, PreferencesRepository
from clipflow.ui.theme import DARK, LIGHT, ThemeManager, build_qss, contrast_ratio

# -- theme tokens ----------------------------------------------------------------------------


@pytest.mark.parametrize("theme", [DARK, LIGHT], ids=["dark", "light"])
def test_text_contrast_meets_wcag_aa(theme):
    for background in (theme.bg, theme.surface, theme.selected, theme.code_bg):
        assert contrast_ratio(theme.text, background) >= 7.0
        assert contrast_ratio(theme.muted, background) >= 4.5, background
    for foreground in (theme.accent, theme.danger, theme.success):
        assert contrast_ratio(foreground, theme.surface) >= 4.5, foreground
    assert contrast_ratio(theme.on_accent, theme.accent) >= 4.5
    assert contrast_ratio(theme.danger, theme.danger_bg) >= 4.5


@pytest.mark.parametrize("theme", [DARK, LIGHT], ids=["dark", "light"])
def test_qss_uses_tokens_and_has_focus_indicators(theme):
    qss = build_qss(theme, chevron="/tmp/x.png")
    assert theme.bg in qss and theme.accent in qss
    assert "QPushButton:focus" in qss and "QLineEdit:focus" in qss
    assert 'url("/tmp/x.png")' in qss
    assert qss.count("{") == qss.count("}")


def test_theme_manager_modes_and_system_following(qapp, monkeypatch):
    manager = ThemeManager(qapp)
    seen = []
    manager.theme_changed.connect(seen.append)
    assert manager.set_mode("dark") is DARK
    assert qapp.palette().color(QPalette.ColorRole.Window).name() == DARK.bg.lower()
    assert manager.set_mode("light") is LIGHT
    assert manager.set_mode("bogus") is not None and manager.mode == "system"

    monkeypatch.setattr(manager, "system_scheme", lambda: Qt.ColorScheme.Dark)
    manager.set_mode("system")
    assert manager.theme is DARK
    monkeypatch.setattr(manager, "system_scheme", lambda: Qt.ColorScheme.Light)
    manager._on_system_scheme_changed(Qt.ColorScheme.Light)  # OS appearance switched
    assert manager.theme is LIGHT
    manager.set_mode("dark")
    manager._on_system_scheme_changed(Qt.ColorScheme.Light)  # ignored when forced
    assert manager.theme is DARK
    assert seen and all(t in (DARK, LIGHT) for t in seen)


# -- preferences ---------------------------------------------------------------------------


def test_preferences_defaults_and_round_trip(conn):
    repo = PreferencesRepository(conn)
    assert repo.load() == UiPreferences()
    prefs = UiPreferences(
        theme="dark", preview_lines=6, hide_after_copy=True, unified_title_bar=False
    )
    repo.save(prefs)
    assert repo.load() == prefs
    keys = {row[0] for row in conn.execute("SELECT key FROM app_settings")}
    assert keys == set(KEYS.values())
    assert all(key.startswith("ui.") for key in keys)


def test_preferences_ignore_bad_values_and_clamp(conn):
    rows = {
        "ui.theme": json.dumps("neon"),
        "ui.preview_lines": json.dumps(99),
        "ui.hide_after_copy": json.dumps("yes"),
        "ui.unified_title_bar": "not json",
    }
    conn.executemany("INSERT INTO app_settings (key, value) VALUES (?, ?)", rows.items())
    prefs = PreferencesRepository(conn).load()
    assert prefs == UiPreferences(theme="system", preview_lines=8)


def test_legacy_recording_keys_are_never_read_or_written(conn):
    conn.executemany(
        "INSERT INTO app_settings (key, value) VALUES (?, ?)",
        [("recording_consent", "true"), ("recording_paused", "false")],
    )
    repo = PreferencesRepository(conn)
    assert repo.load() == UiPreferences()
    repo.save(UiPreferences(theme="dark"))
    legacy = dict(conn.execute("SELECT key, value FROM app_settings WHERE key LIKE 'recording%'"))
    assert legacy == {"recording_consent": "true", "recording_paused": "false"}
    assert not any("record" in name for name in KEYS)
