"""Resolve IANA, Windows and Qt fixed-offset timezone identifiers safely."""

import re
from datetime import timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import QTimeZone


def local_zone(name=""):
    selected = name.strip() or bytes(QTimeZone.systemTimeZoneId()).decode("utf-8", errors="replace")
    if selected in ("UTC", "GMT", "Etc/UTC", "Etc/GMT", "Z"):
        return timezone.utc  # Always available, even in a damaged installation.
    offset = re.fullmatch(r"(?:UTC|GMT)([+-])(\d{2}):(\d{2})(?::(\d{2}))?", selected)
    if offset:
        sign, hours, minutes, seconds = offset.groups()
        h, m, s = int(hours), int(minutes), int(seconds or 0)
        if h < 24 and m < 60 and s < 60:
            delta = timedelta(hours=h, minutes=m, seconds=s)
            return timezone(delta if sign == "+" else -delta)
    # Qt can report a Windows registry name instead of an IANA database key.
    mapped = bytes(QTimeZone.windowsIdToDefaultIanaId(selected.encode("utf-8"))).decode()
    try:
        return ZoneInfo(mapped or selected)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(
            "Timezone unavailable. Choose an IANA timezone such as Asia/Manila or UTC "
            "in Preferences → Reminders and Google. Windows app users: install the latest "
            "complete build. Source users: install the requirements, including tzdata. "
            "No reminder time has been changed."
        ) from None
