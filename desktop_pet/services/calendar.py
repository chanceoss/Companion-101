"""Pure Calendar event normalization; never invent schedules or modify events."""

from datetime import datetime, time, timezone, timedelta
from .reminders import local_zone, local_to_utc


def event_time(value, zone):
    if "dateTime" in value:
        result = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = local_to_utc(
                result, local_zone(value.get("timeZone") or str(zone))
            )
        return result.astimezone(timezone.utc), False
    if "date" in value:
        day = datetime.fromisoformat(value["date"]).date()
        return local_to_utc(datetime.combine(day, time()), zone), True
    raise ValueError("Calendar event has no supported start time.")


def normalize_events(items, zone_name=""):
    zone = local_zone(zone_name)
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get("status") == "cancelled":
            continue
        try:
            start, all_day = event_time(item["start"], zone)
            end, _ = event_time(item.get("end", item["start"]), zone)
            result.append(
                {
                    "id": str(item["id"]),
                    "title": str(item.get("summary", "Untitled event"))[:300],
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "all_day": all_day,
                    "display": start.astimezone(zone).strftime("%Y-%m-%d")
                    + (
                        " · all day"
                        if all_day
                        else start.astimezone(zone).strftime(" · %I:%M %p")
                    ),
                    "notice_key": str(item["id"]) + "|" + start.isoformat(),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(result, key=lambda e: e["start"])


def schedule_summary(events, zone_name="", now=None):
    now = now or datetime.now(timezone.utc)
    zone = local_zone(zone_name)
    today = now.astimezone(zone).date()
    day_start = datetime.combine(today, time(), tzinfo=zone).astimezone(timezone.utc)
    day_end = datetime.combine(
        today + timedelta(days=1), time(), tzinfo=zone
    ).astimezone(timezone.utc)
    today_events = [
        event
        for event in events
        if datetime.fromisoformat(event["start"]) < day_end
        and (
            datetime.fromisoformat(event.get("end", event["start"])) > day_start
            or datetime.fromisoformat(event["start"]) >= day_start
        )
    ]
    upcoming = [
        event for event in events if datetime.fromisoformat(event["start"]) >= now
    ]
    if not today_events:
        text = "Google Calendar reports no events for today."
    else:
        text = f"Google Calendar: {len(today_events)} event(s) today.\n" + "\n".join(
            e["display"] + " · " + e["title"] for e in today_events[:15]
        )
    if upcoming:
        text += "\nNext: " + upcoming[0]["display"] + " · " + upcoming[0]["title"]
    return text
