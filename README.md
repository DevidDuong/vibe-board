# Vibe-Board

A privacy-first command palette for macOS.

Save terminal commands you use often, find them instantly, and copy them when you need them.

Vibe-Board does **not** monitor your clipboard and does **not** execute commands for you.

<!-- Add screenshot here later -->
<!-- ![Vibe-Board](docs/images/vibe-board.png) -->

## Features

- Save and organize frequently used terminal commands
- Fast search by title, command, or description
- Categories and pinned commands
- Global shortcut: `⌃⌥⌘V`
- Light, dark, and system themes
- Multi-monitor window placement
- Local SQLite storage
- Secret detection when saving commands
- Menu-bar access
- Works without VS Code after building the standalone app

## How it works

Save a command:

```bash
kubectl get pods -A
```

Open Vibe-Board with:

```text
⌃⌥⌘V
```

Search for the command, press **Enter** to copy it, then paste it into your terminal yourself.

Vibe-Board never automatically pastes or executes commands.

## Privacy

Vibe-Board is local-first.

- No clipboard monitoring
- No background recording
- No command execution
- No telemetry
- No account
- No network access
- No automatic shell-history import

Your command library is stored locally in SQLite.

The database is not encrypted, so avoid storing passwords, access tokens, private keys, or other secrets directly in commands.

Use environment variables instead:

```bash
curl -H "Authorization: Bearer $API_TOKEN" https://example.com
```

## Requirements

- macOS
- Apple Silicon
- Python 3.12+ for development

## Development

Clone the repository:

```bash
git clone https://github.com/DevidDuong/vibe-board.git
cd vibe-board
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

Run:

```bash
python main.py
```

## Build the macOS app

Build the standalone application:

```bash
./packaging/build_macos.sh
```

The app will be created at:

```text
dist/Vibe-Board.app
```

After building, Vibe-Board can run without VS Code or a Python terminal.

> The current build is Apple Silicon only and is not yet notarized for public macOS distribution.

## Testing

Run the test suite:

```bash
python -m pytest -q
```

Run linting:

```bash
python -m ruff check .
python -m ruff format --check .
```

## Roadmap

Planned improvements include:

- Command placeholders such as `{branch}` and `{namespace}`
- Import/export
- Optional launch at login
- Menu-bar-only mode
- Windows support
- Signed and notarized macOS releases

## Contributing

Issues and pull requests are welcome.

Please open an issue before proposing large architectural changes.

Security and privacy guarantees must not be weakened by contributions.

## License

MIT License. See [LICENSE](LICENSE).
