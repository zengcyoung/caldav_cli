# caldav_cli

CalDAV CLI for OpenClaw — manage Nextcloud (and any CalDAV-compatible) calendar events from the terminal.

Built with [python-caldav](https://github.com/python-caldav/caldav) and [Typer](https://typer.tiangolo.com/). Designed as a safe, discoverable interface for AI agents (OpenClaw) to interact with your calendar without ever exposing credentials in context.

## Features

- 📅 List, create, update, and delete calendar events
- 🔐 Credentials stored securely in `~/.config/caldav_cli/config.env` (chmod 600) — never in code
- 🗂️ Multi-calendar support
- 🤖 Full `--help` on every command for AI agent discoverability
- 📦 Managed with [uv](https://docs.astral.sh/uv/)

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
git clone https://github.com/zengcyoung/caldav_cli.git
cd caldav_cli
uv pip install -e .
```

Then symlink to your PATH:

```bash
ln -sf "$(pwd)/.venv/bin/caldav_cli" ~/.local/bin/caldav_cli
```

## Configuration

### Option 1: Interactive setup wizard

```bash
caldav_cli setup
```

This writes your credentials to `~/.config/caldav_cli/config.env` with mode 600.

### Option 2: Manual config file

Create `~/.config/caldav_cli/config.env`:

```env
CALDAV_URL=https://nextcloud.example.com/remote.php/dav
CALDAV_USERNAME=youruser
CALDAV_PASSWORD=yourapppassword
CALDAV_CALENDAR=personal   # optional — uses first calendar if unset
```

```bash
chmod 600 ~/.config/caldav_cli/config.env
```

### Option 3: Environment variables

```bash
export CALDAV_URL=https://nextcloud.example.com/remote.php/dav
export CALDAV_USERNAME=youruser
export CALDAV_PASSWORD=yourapppassword
```

> **Tip:** If you have 2FA enabled on Nextcloud, generate an **App Password** under  
> Settings → Security → App passwords and use that instead of your main password.

Verify your setup:

```bash
caldav_cli config     # shows which keys are set (no secrets printed)
caldav_cli calendars  # lists available calendars
```

## Usage

```
caldav_cli calendars                          List all calendars
caldav_cli events [OPTIONS]                   List upcoming events
caldav_cli add SUMMARY --start DT [OPTIONS]   Create a new event
caldav_cli show UID                           Show full event details
caldav_cli update UID [OPTIONS]               Update an existing event
caldav_cli delete UID                         Delete an event
caldav_cli config                             Show credential status
caldav_cli setup                              Run the setup wizard
```

**Date format:** `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` (e.g. `2024-06-01T14:30`)

### Examples

```bash
# List events this week
caldav_cli events --start 2024-06-01 --end 2024-06-07

# List next 30 days as JSON
caldav_cli events --output json

# Add an event
caldav_cli add "Doctor appointment" \
  --start 2024-06-03T10:00 \
  --end 2024-06-03T11:00 \
  --location "City Clinic"

# Add to a specific calendar
caldav_cli add "Team standup" --start 2024-06-03T09:00 --calendar work

# Reschedule an event (get UID first)
caldav_cli events --output json
caldav_cli update <UID> --start 2024-06-03T11:00 --end 2024-06-03T12:00

# Delete an event
caldav_cli delete <UID> --yes
```

Every command supports `--help` for full option details:

```bash
caldav_cli events --help
caldav_cli add --help
```

## Project Structure

```
caldav_cli/
├── src/caldav_cli/
│   ├── __init__.py
│   ├── config.py      # credential loading (env vars + config file)
│   ├── client.py      # CalDAV CRUD operations
│   └── main.py        # Typer CLI entrypoint
├── pyproject.toml
└── uv.lock
```

## License

MIT
