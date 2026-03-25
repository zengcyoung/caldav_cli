"""Configuration loader for caldav_cli.

Reads credentials from (in priority order):
1. Environment variables: CALDAV_URL, CALDAV_USERNAME, CALDAV_PASSWORD
2. Config file: ~/.config/caldav_cli/config.env
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values


CONFIG_DIR = Path.home() / ".config" / "caldav_cli"
CONFIG_FILE = CONFIG_DIR / "config.env"


def load_config() -> dict[str, str]:
    """Load and merge config from file + environment variables.

    Environment variables always override config file values.
    """
    file_config: dict[str, str] = {}
    if CONFIG_FILE.exists():
        file_config = {k: v for k, v in dotenv_values(CONFIG_FILE).items() if v is not None}

    # Env vars override file
    env_keys = ("CALDAV_URL", "CALDAV_USERNAME", "CALDAV_PASSWORD", "CALDAV_CALENDAR", "CALDAV_TIMEZONE")
    for key in env_keys:
        val = os.environ.get(key)
        if val is not None:
            file_config[key] = val

    return file_config


def get_credentials() -> tuple[str, str, str]:
    """Return (url, username, password). Raises if any are missing."""
    config = load_config()
    missing = [k for k in ("CALDAV_URL", "CALDAV_USERNAME", "CALDAV_PASSWORD") if not config.get(k)]
    if missing:
        raise ValueError(
            f"Missing credentials: {', '.join(missing)}\n"
            f"Set them via environment variables or in {CONFIG_FILE}\n\n"
            "Example config.env:\n"
            "  CALDAV_URL=https://nextcloud.example.com/remote.php/dav\n"
            "  CALDAV_USERNAME=youruser\n"
            "  CALDAV_PASSWORD=yourapppassword\n"
            "  CALDAV_CALENDAR=personal  # optional, uses default calendar if unset\n"
            "  CALDAV_TIMEZONE=Asia/Shanghai  # optional, falls back to system tz"
        )
    return config["CALDAV_URL"], config["CALDAV_USERNAME"], config["CALDAV_PASSWORD"]


def get_default_calendar_name() -> str | None:
    """Return optional preferred calendar name."""
    config = load_config()
    return config.get("CALDAV_CALENDAR")


def config_path() -> Path:
    return CONFIG_FILE
