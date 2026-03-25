"""CalDAV client helpers — connection, calendar resolution, event CRUD."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone, tzinfo
import zoneinfo
from typing import Optional

import caldav
from icalendar import Calendar, Event


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


# ── Event helpers ────────────────────────────────────────────────────────────


def _parse_dt(value: str, tz: str | None = None) -> datetime:
    """Parse ISO datetime or date string into a timezone-aware datetime.

    Timezone resolution order:
    1. Explicit offset in value (e.g. 2024-06-01T14:30+09:00)
    2. `tz` argument (IANA name, e.g. 'Asia/Shanghai')
    3. CALDAV_TIMEZONE env var (IANA name)
    4. System local timezone
    """
    import os

    # Try parsing with explicit timezone offset first (e.g. +08:00)
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M%z"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    # Parse naive datetime or date
    dt: datetime | None = None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                dt = datetime.combine(parsed.date(), datetime.min.time())
            else:
                dt = parsed
            break
        except ValueError:
            continue

    if dt is None:
        raise ValueError(
            f"Cannot parse datetime: '{value}'. "
            "Use YYYY-MM-DD, YYYY-MM-DDTHH:MM, or YYYY-MM-DDTHH:MM+HH:MM"
        )

    # Resolve timezone
    tz_name = tz or os.environ.get("CALDAV_TIMEZONE")
    if tz_name:
        try:
            local_tz = zoneinfo.ZoneInfo(tz_name)
            return dt.replace(tzinfo=local_tz)
        except zoneinfo.ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: '{tz_name}'. Use IANA names like 'Asia/Shanghai'.")

    # Fall back to system local timezone
    local_tz = datetime.now().astimezone().tzinfo
    return dt.replace(tzinfo=local_tz)


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
    """Create an event. Returns the new UID."""
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
        event.add("description", description)
    if location:
        event.add("location", location)

    cal.add_component(event)
    calendar.add_event(cal.to_ical().decode())
    return uid


def _find_event_obj(calendar: caldav.Calendar, uid: str) -> caldav.CalendarObjectResource:
    """Find a CalDAV event object by UID."""
    # Search broad range and match by UID
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
    """Update an existing event by UID."""
    obj = _find_event_obj(calendar, uid)
    cal = Calendar.from_ical(obj.data)

    for component in cal.walk():
        if component.name == "VEVENT" and str(component.get("uid", "")) == uid:
            if summary is not None:
                component["summary"] = summary
            if start is not None:
                dt = _parse_dt(start, tz=tz)
                component.pop("dtstart", None)
                component.add("dtstart", dt)
            if end is not None:
                dt = _parse_dt(end, tz=tz)
                component.pop("dtend", None)
                component.add("dtend", dt)
            if description is not None:
                component["description"] = description
            if location is not None:
                component["location"] = location
            break

    obj.data = cal.to_ical().decode()
    obj.save()


def delete_event(calendar: caldav.Calendar, uid: str) -> None:
    """Delete an event by UID."""
    obj = _find_event_obj(calendar, uid)
    obj.delete()
