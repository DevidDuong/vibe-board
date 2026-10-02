"""Best-effort detection of recognizable secrets in text the user is about to save.

This is a safety net, not a guarantee. It recognizes common *formats* (private key headers,
well-known token prefixes, ``password=…`` style assignments, credentials in URLs). It cannot
recognize an arbitrary password, a token with an unknown format, or a secret split across
lines or variables. Findings name the kind of secret and the field only — never the value.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    BLOCK = "block"  # cannot be saved
    WARN = "warn"  # can be saved after explicit confirmation


@dataclass(frozen=True, slots=True)
class SecretFinding:
    kind: str
    field: str
    severity: Severity


def _is_placeholder(value: str) -> bool:
    """Variable references and obvious placeholders are not secrets."""
    value = value.strip("'\"")
    if not value or value[0] in "$<{%":
        return True
    return set(value) <= set("*xX.") or value.lower() in {"password", "changeme", "secret"}


@dataclass(frozen=True, slots=True)
class _Rule:
    kind: str
    severity: Severity
    pattern: re.Pattern[str]
    value_group: int | None = None  # if set, skip matches whose value is a placeholder

    def matches(self, text: str) -> bool:
        for match in self.pattern.finditer(text):
            if self.value_group is None or not _is_placeholder(match.group(self.value_group)):
                return True
        return False


_ASSIGN_NAME = r"[A-Za-z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY)"

RULES: tuple[_Rule, ...] = (
    _Rule(
        "Private key",
        Severity.BLOCK,
        re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"),
    ),
    _Rule("AWS access key ID", Severity.WARN, re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    _Rule(
        "GitHub token",
        Severity.WARN,
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
    ),
    _Rule("GitLab token", Severity.WARN, re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}")),
    _Rule("Slack token", Severity.WARN, re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    _Rule("Stripe live key", Severity.WARN, re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
    _Rule("Google API key", Severity.WARN, re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    _Rule("API secret key (sk-…)", Severity.WARN, re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    _Rule(
        "JSON Web Token",
        Severity.WARN,
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ),
    _Rule(
        "Password in URL",
        Severity.WARN,
        re.compile(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://[^\s/:@]+:([^\s/@]+)@"),
        value_group=1,
    ),
    _Rule(
        "Authorization header",
        Severity.WARN,
        re.compile(r"(?i)\bauthorization:\s*(?:bearer|basic|token)\s+([^\s'\"]{8,})"),
        value_group=1,
    ),
    _Rule(
        "Password or secret assignment",
        Severity.WARN,
        re.compile(rf"(?i)\b{_ASSIGN_NAME}[A-Za-z0-9_]*\s*[:=]\s*(['\"]?[^\s'\"]{{4,}})"),
        value_group=1,
    ),
    _Rule(
        "Password option",
        Severity.WARN,
        re.compile(
            r"(?i)(?:--password|--passwd|--token|--api-key|--secret|\bsshpass\s+-p)"
            r"(?:=|\s+)(['\"]?[^\s'\"]{4,})"
        ),
        value_group=1,
    ),
)


def scan_text(text: str, field: str) -> list[SecretFinding]:
    return [
        SecretFinding(kind=rule.kind, field=field, severity=rule.severity)
        for rule in RULES
        if rule.matches(text)
    ]


def scan_fields(fields: Mapping[str, str]) -> list[SecretFinding]:
    findings: list[SecretFinding] = []
    for field, text in fields.items():
        findings.extend(scan_text(text, field))
    return findings


SecretScanner = Callable[[Mapping[str, str]], list[SecretFinding]]
