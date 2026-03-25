---
name: caldav
description: "Manage calendar events via CalDAV (Nextcloud, Radicale, iCloud, Fastmail, etc.) using the local caldav_cli tool. Use when the user asks to check their schedule, list events, add/create/schedule meetings or appointments, update or reschedule events, delete events, or proactively surface upcoming calendar items. Credentials are stored securely in ~/.config/caldav_cli/config.env (never printed). Supports multiple calendars."
metadata:
  {
    "openclaw": { "emoji": "📅", "requires": { "bins": ["caldav_cli"] } },
  }
---

# CalDAV Skill

Interact with the user's CalDAV calendar via `caldav_cli`.

## Installation

If `caldav_cli` is not yet installed:

```bash
git clone https://github.com/zengcyoung/caldav_cli.git
cd caldav_cli
uv pip install -e .
ln -sf "$(pwd)/.venv/bin/caldav_cli" ~/.local/bin/caldav_cli
caldav_cli setup   # interactive credential wizard
```

Or copy this `SKILL.md` into your OpenClaw skills directory:

```bash
mkdir -p ~/.openclaw/skills/caldav
cp SKILL.md ~/.openclaw/skills/caldav/SKILL.md
```

## Quick Reference

```
caldav_cli calendars                          # list all calendars
caldav_cli events [--start DATE] [--end DATE] [--calendar NAME] [--output json]
caldav_cli add SUMMARY --start DT [--end DT] [--desc TEXT] [--location TEXT] [--calendar NAME]
caldav_cli show UID [--output json]
caldav_cli update UID [--summary TEXT] [--start DT] [--end DT] [--desc TEXT] [--location TEXT]
caldav_cli delete UID --yes
caldav_cli config                             # check credential status (no secrets shown)
caldav_cli setup                              # interactive credential wizard
```

**DATE FORMAT:** `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` (e.g. `2024-06-01T14:30`)
**UID:** UUID from `events` or `show` output — always required for update/delete.

## Workflows

### Check upcoming schedule
```bash
caldav_cli events                             # today → +30 days
caldav_cli events --start 2024-06-01 --end 2024-06-07   # specific week
caldav_cli events --output json               # machine-readable
```

### Add an event
```bash
caldav_cli add "Doctor appointment" --start 2024-06-03T10:00 --end 2024-06-03T11:00 --location "City Clinic"
caldav_cli add "Team standup" --start 2024-06-03T09:00 --end 2024-06-03T09:30 --calendar work
```

### Update or reschedule
```bash
# First get the UID:
caldav_cli events --output json | grep -A5 "Team standup"
# Then update:
caldav_cli update <UID> --start 2024-06-03T10:00 --end 2024-06-03T10:30
```

### Delete an event
```bash
caldav_cli delete <UID> --yes
```

## Credential Setup (first-time only)
```bash
caldav_cli setup      # interactive wizard
caldav_cli config     # verify status (no secrets printed)
```

Config stored at: `~/.config/caldav_cli/config.env` (chmod 600, never logged).

Supported providers: Nextcloud, Radicale, Baikal, iCloud, Fastmail, any standard CalDAV server.

## Tips
- Always get UID from `events --output json` before update/delete — never guess.
- If calendar name is unclear, run `caldav_cli calendars` first.
- Use `--output json` when parsing output programmatically.
- Default calendar = first one found, or `CALDAV_CALENDAR` env var.
- For Nextcloud: use an **App Password** (Settings → Security → App passwords), not your main password.
