"""CalDAV client helpers — connection, calendar resolution, event CRUD.

Timezone design (RFC 5545 compliant):
- All datetimes are stored with IANA TZID (e.g. DTSTART;TZID=Asia/Tokyo:20260330T120000)
- Fixed UTC offsets (+09:00) are mapped to canonical IANA names when possible
- update_event inherits the original event's TZID when --tz is not specified
- UTC offset fallback only used when no IANA mapping is found
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import zoneinfo

import caldav
from icalendar import Calendar, Event


# ── Connection ────────────────────────────────────────────────────────────────

def connect(url: str, username: str, password: str) -> caldav.DAVClient:
    return caldav.DAVClient(url=url, username=username, password=password)


def get_principal(client: caldav.DAVClient) -> caldav.Principal:
    return client.principal()


def list_calendars(principal: caldav.Principal) -> list[caldav.Calendar]:
    return principal.calendars()


def resolve_calendar(
    principal: caldav.Principal,
    name: str | None = None,
) -> caldav.Calendar:
    """Return calendar by name, or the first/default one."""
    calendars = list_calendars(principal)
    if not calendars:
        raise RuntimeError("No calendars found on server.")
    if name:
        for cal in calendars:
            if cal.name and cal.name.lower() == name.lower():
                return cal
        raise RuntimeError(
            f"Calendar '{name}' not found. "
            f"Available: {', '.join(c.name or '?' for c in calendars)}"
        )
    return calendars[0]


# ── Timezone helpers ──────────────────────────────────────────────────────────

# Common UTC offset → IANA mapping for fallback
_OFFSET_TO_IANA: dict[int, str] = {
    -12: "Etc/GMT+12",
    -11: "Pacific/Pago_Pago",
    -10: "Pacific/Honolulu",
    -9:  "America/Anchorage",
    -8:  "America/Los_Angeles",
    -7:  "America/Denver",
    -6:  "America/Chicago",
    -5:  "America/New_York",
    -4:  "America/Halifax",
    -3:  "America/Sao_Paulo",
    -2:  "Atlantic/South_Georgia",
    -1:  "Atlantic/Azores",
     0:  "UTC",
     1:  "Europe/Paris",
     2:  "Europe/Helsinki",
     3:  "Europe/Moscow",
     4:  "Asia/Dubai",
     5:  "Asia/Karachi",
     6:  "Asia/Dhaka",
     7:  "Asia/Bangkok",
     8:  "Asia/Shanghai",
     9:  "Asia/Tokyo",
    10:  "Australia/Sydney",
    11:  "Pacific/Noumea",
    12:  "Pacific/Auckland",
}


def _offset_to_zoneinfo(offset_seconds: int) -> zoneinfo.ZoneInfo:
    """Convert a UTC offset (seconds) to a ZoneInfo, preferring IANA names."""
    hours = offset_seconds // 3600
    iana = _OFFSET_TO_IANA.get(hours)
    if iana:
        return zoneinfo.ZoneInfo(iana)
    # Fall back to Etc/GMT notation (note: sign is inverted)
    sign = "+" if hours <= 0 else "-"
    return zoneinfo.ZoneInfo(f"Etc/GMT{sign}{abs(hours)}")


def _ensure_zoneinfo(dt: datetime) -> datetime:
    """Ensure a datetime uses ZoneInfo (IANA) rather than a fixed UTC offset tzinfo.

    This is important for RFC 5545 compliance: TZID must be an IANA name,
    not a numeric offset like 'UTC+09:00'.
    """
    if dt.tzinfo is None:
        return dt
    # Already a ZoneInfo — no conversion needed
    if isinstance(dt.tzinfo, zoneinfo.ZoneInfo):
        return dt
    # Convert fixed offset → ZoneInfo
    offset = dt.utcoffset()
    if offset is not None:
        zi = _offset_to_zoneinfo(int(offset.total_seconds()))
        return dt.replace(tzinfo=zi)
    return dt


def _get_event_tzid(component) -> str | None:
    """Extract the TZID from a VEVENT's DTSTART property, if present."""
    dtstart = component.get("dtstart")
    if not dtstart:
        return None
    # Check params for explicit TZID
    if hasattr(dtstart, "params") and "TZID" in dtstart.params:
        tzid = dtstart.params["TZID"]
        # Prefer it if it's a valid IANA name
        try:
            zoneinfo.ZoneInfo(tzid)
            return tzid
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            pass
    # Check tzinfo on the datetime itself
    dt = dtstart.dt
    if isinstance(dt, datetime) and isinstance(dt.tzinfo, zoneinfo.ZoneInfo):
        return dt.tzinfo.key
    return None


def _parse_dt(value: str, tz: str | None = None) -> datetime:
    """Parse ISO datetime string into a ZoneInfo-aware datetime (RFC 5545 compliant).

    Timezone resolution order:
    1. `tz` argument (IANA name, e.g. 'Asia/Tokyo') — explicit override
    2. CALDAV_TIMEZONE env var (IANA name)
    3. Explicit offset in value (+09:00) → mapped to IANA via _OFFSET_TO_IANA
    4. System local timezone → converted to ZoneInfo if possible
    """
    # Resolve explicit tz name first (overrides everything)
    tz_name = tz or os.environ.get("CALDAV_TIMEZONE")

    # Try parsing with explicit timezone offset (e.g. 2026-03-30T12:00+09:00)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z"):
        try:
            dt = datetime.strptime(value, fmt)
            if tz_name:
                # Explicit tz overrides the offset in the string
                return dt.replace(tzinfo=zoneinfo.ZoneInfo(tz_name))
            return _ensure_zoneinfo(dt)
        except ValueError:
            continue

    # Parse naive datetime or date
    dt = None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            dt = datetime.combine(parsed.date(), datetime.min.time()) if fmt == "%Y-%m-%d" else parsed
            break
        except ValueError:
            continue

    if dt is None:
        raise ValueError(
            f"Cannot parse datetime: '{value}'. "
            "Use YYYY-MM-DD, YYYY-MM-DDTHH:MM, or YYYY-MM-DDTHH:MM+HH:MM"
        )

    if tz_name:
        try:
            return dt.replace(tzinfo=zoneinfo.ZoneInfo(tz_name))
        except (zoneinfo.ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"Unknown timezone: '{tz_name}'. Use IANA names like 'Asia/Shanghai'.")

    # Fall back to system local timezone, converted to ZoneInfo
    local_dt = dt.astimezone()
    return _ensure_zoneinfo(local_dt)


# ── Event dict helpers ────────────────────────────────────────────────────────

def _unescape_text(value: str) -> str:
    """Convert literal \\n sequences to real newlines.

    Shell arguments pass '\\n' as two characters (backslash + n).
    """
    return value.replace("\\n", "\n")


def _event_to_dict(vevent) -> dict:
    """Extract key fields from a vEvent component."""
    def _str(val):
        return str(val) if val else None

    summary = _str(vevent.get("summary"))
    dtstart = vevent.get("dtstart")
    dtend = vevent.get("dtend")
    uid = _str(vevent.get("uid"))
    description = _str(vevent.get("description"))
    location = _str(vevent.get("location"))

    start = dtstart.dt if dtstart else None
    end = dtend.dt if dtend else None

    return {
        "uid": uid,
        "summary": summary,
        "start": str(start) if start else None,
        "end": str(end) if end else None,
        "description": description,
        "location": location,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

def fetch_events(
    calendar: caldav.Calendar,
    start: str | None = None,
    end: str | None = None,
) -> list[dict]:
    """Fetch events in a date range (defaults to today → +30 days)."""
    now = datetime.now(tz=timezone.utc)
    dt_start = _parse_dt(start) if start else now.replace(hour=0, minute=0, second=0)
    dt_end = _parse_dt(end) if end else dt_start + timedelta(days=30)

    results = calendar.date_search(start=dt_start, end=dt_end, expand=True)
    events = []
    for obj in results:
        cal = Calendar.from_ical(obj.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                events.append(_event_to_dict(component))
    events.sort(key=lambda e: e.get("start") or "")
    return events


def create_event(
    calendar: caldav.Calendar,
    summary: str,
    start: str,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    tz: str | None = None,
) -> str:
    """Create an event with RFC 5545 compliant TZID. Returns the new UID."""
    dt_start = _parse_dt(start, tz=tz)
    dt_end = _parse_dt(end, tz=tz) if end else dt_start + timedelta(hours=1)
    uid = str(uuid.uuid4())

    cal = Calendar()
    cal.add("prodid", "-//caldav_cli//EN")
    cal.add("version", "2.0")

    event = Event()
    event.add("uid", uid)
    event.add("summary", summary)
    event.add("dtstart", dt_start)
    event.add("dtend", dt_end)
    event.add("dtstamp", datetime.now(tz=timezone.utc))
    if description:
        event.add("description", _unescape_text(description))
    if location:
        event.add("location", location)

    cal.add_component(event)
    calendar.add_event(cal.to_ical().decode())
    return uid


def _find_event_obj(calendar: caldav.Calendar, uid: str) -> caldav.CalendarObjectResource:
    """Find a CalDAV event object by UID."""
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = datetime(2099, 12, 31, tzinfo=timezone.utc)
    for obj in calendar.date_search(start=start, end=end):
        cal = Calendar.from_ical(obj.data)
        for component in cal.walk():
            if component.name == "VEVENT":
                if str(component.get("uid", "")) == uid:
                    return obj
    raise RuntimeError(f"Event with UID '{uid}' not found.")


def update_event(
    calendar: caldav.Calendar,
    uid: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
    location: str | None = None,
    tz: str | None = None,
) -> None:
    """Update an existing event by UID.

    Timezone handling:
    - If --tz is provided: use that IANA timezone for new start/end
    - If --tz is not provided: inherit the original event's TZID
    - This ensures we never silently change a local-time event to UTC
    """
    obj = _find_event_obj(calendar, uid)
    cal = Calendar.from_ical(obj.data)

    for component in cal.walk():
        if component.name == "VEVENT" and str(component.get("uid", "")) == uid:
            # Determine effective timezone: explicit --tz > original event TZID > CALDAV_TIMEZONE > system
            effective_tz = tz or _get_event_tzid(component) or os.environ.get("CALDAV_TIMEZONE")

            if summary is not None:
                component["summary"] = summary
            if start is not None:
                dt = _parse_dt(start, tz=effective_tz)
                component.pop("dtstart", None)
                component.add("dtstart", dt)
            if end is not None:
                dt = _parse_dt(end, tz=effective_tz)
                component.pop("dtend", None)
                component.add("dtend", dt)
            if description is not None:
                component["description"] = _unescape_text(description)
            if location is not None:
                component["location"] = location
            break

    obj.data = cal.to_ical().decode()
    obj.save()


def delete_event(calendar: caldav.Calendar, uid: str) -> None:
    """Delete an event by UID."""
    obj = _find_event_obj(calendar, uid)
    obj.delete()

