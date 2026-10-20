import json
import math
import os
import sys
from copy import deepcopy
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PySide6.QtCore import QStandardPaths

DEFAULTS = {
    "scale": 100,
    "wander": False,
    "reminders": False,
    "chat_reactions": True,
    "name": "Biscuit",
    "provider": False,
    "endpoint": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "ai_provider": "custom",
    "provider_profiles": {},
    "ai_fallback": False,
    "ai_max_tokens": 400,
    "ai_temperature": 0.7,
    "ai_daily_limit": 0,
    "ai_usage": {},
    "weather_enabled": False,
    "weather_reactions": False,
    "weather_interval": 30,
    "weather_latitude": None,
    "weather_longitude": None,
    "weather_city": "",
    "system_enabled": False,
    "battery_notifications": False,
    "notifications": True,
    "voice_mode": "text",
    "voice_muted": False,
    "voice_volume": 70,
    "voice_speed": 1.0,
    "voice_python": "",
    "piper_model": "",
    "whisper_model": "",
    "voice_language": "",
    "microphone_device": "",
    "reminder_timezone": "",
    "reminder_quiet_focus": True,
    "google_client_file": "",
    "google_python": "",
    "google_tasks_enabled": False,
    "google_calendar_enabled": False,
    "calendar_notifications": False,
    "calendar_reminder_minutes": 10,
    "trivia_enabled": False,
    "trivia_total": 0,
    "trivia_correct": 0,
    "trivia_daily_date": "",
    "trivia_daily_answered": False,
}


def normalize_settings(raw):
    """Whitelist persisted nonsecret fields and recover malformed old values."""
    result = deepcopy(DEFAULTS)
    if isinstance(raw, dict):
        result.update(
            {
                key: value
                for key, value in raw.items()
                if key in DEFAULTS or key in ("x", "y")
            }
        )
    for key, default in DEFAULTS.items():
        if isinstance(default, bool):
            result[key] = result[key] is True
        elif isinstance(default, str):
            if not isinstance(result[key], str):
                result[key] = default
            result[key] = result[key][:4096]
    result["name"] = result["name"][:30].strip() or "Biscuit"
    for key in ("x", "y"):
        if key in result and (
            isinstance(result[key], bool) or not isinstance(result[key], int)
        ):
            result.pop(key)
    ranges = {
        "scale": (60, 150),
        "ai_max_tokens": (32, 4096),
        "ai_daily_limit": (0, 10000),
        "weather_interval": (15, 180),
        "voice_volume": (0, 100),
        "calendar_reminder_minutes": (0, 60),
        "trivia_total": (0, 1000000000),
        "trivia_correct": (0, 1000000000),
    }
    for key, (low, high) in ranges.items():
        try:
            if isinstance(result[key], bool):
                raise ValueError()
            result[key] = min(high, max(low, int(result[key])))
        except (ValueError, TypeError, OverflowError):
            result[key] = DEFAULTS[key]
    for key, low, high in (("ai_temperature", 0, 2), ("voice_speed", 0.5, 2)):
        try:
            value = float(result[key])
            if isinstance(result[key], bool) or not math.isfinite(value):
                raise ValueError()
            result[key] = min(high, max(low, value))
        except (ValueError, TypeError, OverflowError):
            result[key] = DEFAULTS[key]
    for key, low, high in (
        ("weather_latitude", -90, 90),
        ("weather_longitude", -180, 180),
    ):
        value = result[key]
        result[key] = (
            value
            if (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(value)
                and low <= value <= high
            )
            else None
        )
    if result["weather_latitude"] is None or result["weather_longitude"] is None:
        result["weather_enabled"] = False
    if result["ai_provider"] not in ("offline", "custom", "ollama", "groq"):
        result["ai_provider"] = "custom"
    if result["voice_mode"] not in ("text", "spoken", "ptt"):
        result["voice_mode"] = "text"
    if result["voice_language"] not in ("", "en", "tl"):
        result["voice_language"] = ""
    if result["reminder_timezone"]:
        try:
            ZoneInfo(result["reminder_timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            result["reminder_timezone"] = ""
    profiles = result["provider_profiles"]
    result["provider_profiles"] = (
        {
            key: {
                field: value[field][:2048]
                for field in ("endpoint", "model")
                if isinstance(value.get(field), str)
            }
            for key, value in profiles.items()
            if key in ("custom", "ollama", "groq") and isinstance(value, dict)
        }
        if isinstance(profiles, dict)
        else {}
    )
    usage = result["ai_usage"]
    try:
        day = date.fromisoformat(usage["day"]).isoformat()
        count = max(0, min(1000000000, int(usage["count"])))
        result["ai_usage"] = {"day": day, "count": count}
    except (TypeError, KeyError, ValueError, OverflowError):
        result["ai_usage"] = {}
    result["trivia_correct"] = min(result["trivia_correct"], result["trivia_total"])
    return result


class Settings:
    def __init__(self, directory=None):
        self.directory = Path(
            directory
            or QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
        )
        self.path = self.directory / "settings.json"
        loaded = {}
        try:
            if self.path.stat().st_size <= 2 * 1024 * 1024:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self.values = normalize_settings(loaded)

    def get(self, key):
        return self.values.get(key)

    def update(self, **values):
        snapshot = normalize_settings(dict(self.values, **values))
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(snapshot, indent=2, allow_nan=False), encoding="utf-8"
        )
        os.replace(temp, self.path)
        self.values = snapshot


def startup_enabled():
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
        ) as key:
            winreg.QueryValueEx(key, "BiscuitCompanion")
        return True
    except OSError:
        return False


def set_startup(enabled):
    if sys.platform != "win32":
        raise OSError("Windows startup is only available on Windows.")
    import subprocess
    import winreg

    args = [sys.executable]
    if not getattr(sys, "frozen", False):
        args.append(str(Path(__file__).resolve().parent.parent / "run_pet.py"))
    args.append("--startup")
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
    ) as key:
        if enabled:
            winreg.SetValueEx(
                key, "BiscuitCompanion", 0, winreg.REG_SZ, subprocess.list2cmdline(args)
            )
        else:
            try:
                winreg.DeleteValue(key, "BiscuitCompanion")
            except FileNotFoundError:
                pass
