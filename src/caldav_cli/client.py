"""CalDAV client helpers — connection, calendar resolution, event CRUD."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
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


def _parse_dt(value: str) -> datetime:
    """Parse ISO datetime or date string into a timezone-aware datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt == "%Y-%m-%d":
                dt = datetime.combine(dt.date(), datetime.min.time())
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse datetime: '{value}'. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM")


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
) -> str:
    """Create an event. Returns the new UID."""
    dt_start = _parse_dt(start)
    dt_end = _parse_dt(end) if end else dt_start + timedelta(hours=1)
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
) -> None:
    """Update an existing event by UID."""
    obj = _find_event_obj(calendar, uid)
    cal = Calendar.from_ical(obj.data)

    for component in cal.walk():
        if component.name == "VEVENT" and str(component.get("uid", "")) == uid:
            if summary is not None:
                component["summary"] = summary
            if start is not None:
                component["dtstart"] = caldav.vDatetime(_parse_dt(start))
            if end is not None:
                component["dtend"] = caldav.vDatetime(_parse_dt(end))
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
