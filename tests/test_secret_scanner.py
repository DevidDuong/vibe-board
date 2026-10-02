"""Secret detection tests. All "secrets" are synthetic and assembled at runtime so no
realistic credential literal appears in the repository."""

from __future__ import annotations

import pytest

from clipflow.services.secret_scanner import Severity, scan_text

X = "x" * 40
FAKE = {
    "private_key": "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nAAAAfake\n-----END",
    "rsa_key": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "aws": "AKIA" + "FAKEFAKEFAKEFAKE",
    "github": "ghp_" + "Fake" * 9,
    "github_pat": "github_pat_" + "Fake_" * 6,
    "gitlab": "glpat-" + "fake" * 6,
    "slack": "xoxb-" + "0000-fake-fake",
    "stripe": "sk_" + "live_" + "Fake" * 6,
    "google": "AIza" + "F" * 35,
    "sk": "sk-" + "fake" * 8,
    "jwt": "eyJ" + "fakeheader" + ".eyJ" + "fakepayload" + "." + "fakesignature",
}


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (FAKE["private_key"], "Private key"),
        (f"echo '{FAKE['rsa_key']}' > id_rsa", "Private key"),
        (f"export AWS_ACCESS_KEY_ID={FAKE['aws']}", "AWS access key ID"),
        (f"git clone https://{FAKE['github']}@github.com/o/r", "GitHub token"),
        (f"gh auth login --with-token {FAKE['github_pat']}", "GitHub token"),
        (f"curl -H 'PRIVATE-TOKEN: {FAKE['gitlab']}' api", "GitLab token"),
        (f"SLACK={FAKE['slack']}", "Slack token"),
        (f"stripe login --api-key {FAKE['stripe']}", "Stripe live key"),
        (f"curl 'maps?key={FAKE['google']}'", "Google API key"),
        (f"OPENAI={FAKE['sk']}", "API secret key (sk-…)"),
        (f"curl -H 'X: {FAKE['jwt']}'", "JSON Web Token"),
        ("psql postgres://admin:fakepass123@db:5432/app", "Password in URL"),
        ("curl -H 'Authorization: Bearer fakefakefake123'", "Authorization header"),
        ("export DB_PASSWORD='fake-pass-1'", "Password or secret assignment"),
        ("MY_API_KEY=fakevalue npm start", "Password or secret assignment"),
        ("mysql --password=fakepass db", "Password option"),
        ("sshpass -p fakepass ssh host", "Password option"),
    ],
)
def test_recognizes_common_secret_formats(text, kind):
    kinds = {f.kind for f in scan_text(text, "Command")}
    assert kind in kinds


def test_private_key_blocks_others_warn():
    [key] = scan_text(FAKE["private_key"], "Command")
    assert key.severity is Severity.BLOCK
    [token] = scan_text(FAKE["aws"], "Command")
    assert token.severity is Severity.WARN


@pytest.mark.parametrize(
    "text",
    [
        "git log --oneline --graph --all",
        'docker run --rm -it -v "$PWD":/app node:20 npm test',
        "export GITHUB_TOKEN=$(gh auth token)",
        'curl -H "Authorization: Bearer $API_TOKEN" https://api.example.com',
        "psql postgres://admin:$PGPASSWORD@db:5432/app",
        "mysql --password=<your-password> db",
        "export DB_PASSWORD=${DB_PASSWORD:?}",
        "ssh git@github.com",
        "kubectl get secrets -n prod",
        "task-runner --tokenize file.txt",
        "PASSWORD=****",
        X,
    ],
)
def test_ordinary_commands_and_placeholders_are_not_flagged(text):
    assert scan_text(text, "Command") == []


def test_findings_never_contain_the_value():
    findings = scan_text(f"export T={FAKE['github']}", "Command")
    assert findings
    for finding in findings:
        assert FAKE["github"] not in repr(finding)
