# AGENTS.md — Coding Agent Context

This file provides context for AI coding agents (OpenClaw, Codex, Claude Code, etc.) working on this project.

## Project Purpose

`caldav_cli` is a **thin, safe CalDAV CLI wrapper** designed primarily for use by OpenClaw (an AI personal assistant). Its goal is to let an AI agent interact with a user's Nextcloud (or any CalDAV) calendar without ever having credentials leak into conversation context.

**Design priorities, in order:**
1. **Security** — credentials never appear in output, logs, or exceptions
2. **Discoverability** — every command has full `--help`; `--output json` available everywhere for machine parsing
3. **Correctness** — CRUD operations must be reliable; never silently succeed on failure
4. **Simplicity** — thin wrapper around `python-caldav`; avoid over-engineering

## Architecture

```
src/caldav_cli/
├── config.py     Credential loading only. No CalDAV logic.
├── client.py     All CalDAV operations. No CLI/UI logic.
└── main.py       Typer CLI. No business logic — delegates to client.py.
```

**Strict separation of concerns.** Do not mix layers:
- `config.py` → reads credentials, nothing else
- `client.py` → pure CalDAV CRUD, takes explicit args, no config reads
- `main.py` → UI only: parses args, calls client, formats output

## Code Style

- **Python 3.13+**, type hints everywhere (`from __future__ import annotations`)
- **No bare `except`** — always catch specific exceptions or `Exception` with a clear message
- **Never print credentials** — not in errors, not in debug output, not in stack traces; catch auth errors and show a sanitized message
- `rprint()` (Rich) for user-facing output; `err.print()` for errors to stderr
- `--output json` on list/show commands → raw `json.dumps`, no Rich formatting
- Docstrings on all public functions; imperative voice ("Return X", "Raise if Y")
- Line length: 100 chars

## Key Conventions

### Date handling
All datetimes are stored and passed as **UTC-aware `datetime` objects** internally. The `_parse_dt()` helper in `client.py` handles user input; always use it — do not call `datetime.strptime` directly in CLI code.

### UIDs
CalDAV event UIDs are the canonical identifier. Always fetch UIDs via `events --output json` before update/delete. Never construct or guess UIDs.

### Calendar resolution
`resolve_calendar()` in `client.py` handles name matching (case-insensitive) and falls back to the first calendar. Always go through this function — do not traverse `principal.calendars()` directly in `main.py`.

### Error handling pattern
```python
try:
    result = dav.some_operation(...)
    rprint("[green]✓ Done.[/green]")
except Exception as e:
    err.print(f"Error: {e}")
    raise typer.Exit(1)
```
- Always exit with code 1 on error
- Never swallow exceptions silently
- Sanitize error messages — ensure no credential strings can appear (e.g. from URLs with embedded passwords)

## Adding New Commands

1. Add business logic to `client.py` as a standalone function
2. Add the CLI command to `main.py` using `@app.command()`
3. Update the **QUICK REFERENCE** block at the top of `main.py.__doc__` — this is what OpenClaw reads to discover available commands without loading full `--help`
4. Add `--output json` support if the command returns data
5. Update README.md usage table and examples

## Testing

No automated test suite yet. When adding tests:
- Use `pytest`
- Mock CalDAV server responses — do not make real network calls in tests
- Add `pytest` to `[project.optional-dependencies]` in `pyproject.toml` under `[test]`
- Run with: `uv run pytest`

## Dependencies

| Package | Purpose |
|---|---|
| `caldav` | CalDAV protocol client |
| `typer` | CLI framework |
| `rich` | Terminal formatting |
| `python-dotenv` | `.env` config file parsing |
| `icalendar` | iCal object construction (transitive via caldav, used directly in `client.py`) |

Avoid adding new dependencies unless necessary. Prefer stdlib solutions.

## Credential Config

Credentials are read from (priority order):
1. Environment variables: `CALDAV_URL`, `CALDAV_USERNAME`, `CALDAV_PASSWORD`, `CALDAV_CALENDAR`
2. `~/.config/caldav_cli/config.env` (dotenv format, chmod 600)

Config logic lives entirely in `config.py`. Do not read env vars anywhere else.

## OpenClaw Integration

The companion skill lives at:
`~/.asdf/installs/nodejs/24.14.0/lib/node_modules/openclaw/skills/caldav/SKILL.md`

When adding new commands or changing the CLI interface, update the QUICK REFERENCE in `main.py.__doc__` first — OpenClaw reads this to discover commands. The skill's `SKILL.md` may also need updating if workflows change.
