import json
from copy import deepcopy
import os
from pathlib import Path
import sys
from PySide6.QtCore import QStandardPaths

DEFAULTS = {"scale": 100, "wander": False, "reminders": False,
            "name": "Biscuit", "provider": False,
            "endpoint": "https://api.openai.com/v1", "model": "gpt-4o-mini",
            "ai_provider": "custom", "provider_profiles": {}, "ai_fallback": False,
            "ai_max_tokens": 400, "ai_temperature": .7, "ai_daily_limit": 0, "ai_usage": {},
            "weather_enabled": False, "weather_reactions": False, "weather_interval": 30,
            "weather_latitude": None, "weather_longitude": None, "weather_city": "",
            "system_enabled": False, "battery_notifications": False, "notifications": True,
            "voice_mode": "text", "voice_muted": False, "voice_volume": 70, "voice_speed": 1.0,
            "voice_python": "", "piper_model": "", "whisper_model": "", "voice_language": "",
            "microphone_device": "", "reminder_timezone": "", "reminder_quiet_focus": True,
            "google_client_file": "", "google_python": "", "google_tasks_enabled": False,
            "google_calendar_enabled": False, "calendar_notifications": False, "calendar_reminder_minutes": 10}


class Settings:
    def __init__(self, directory=None):
        self.directory = Path(directory or QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
        self.path = self.directory / "settings.json"
        self.values = deepcopy(DEFAULTS)
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.values.update({k: v for k, v in loaded.items() if k in DEFAULTS or k in ("x", "y")})
        except (OSError, ValueError):
            pass
        try:
            self.values["scale"] = min(150, max(60, int(self.values["scale"])))
        except (ValueError, TypeError):
            self.values["scale"] = 100
        for key in ("wander", "reminders", "provider", "ai_fallback", "weather_enabled", "weather_reactions",
                    "system_enabled", "battery_notifications", "notifications", "voice_muted", "reminder_quiet_focus",
                    "google_tasks_enabled", "google_calendar_enabled", "calendar_notifications"):
            self.values[key] = self.values[key] is True
        for key in ("name", "endpoint", "model"):
            if not isinstance(self.values[key], str):
                self.values[key] = DEFAULTS[key]
        for key in ("x", "y"):
            if key in self.values and not isinstance(self.values[key], int):
                del self.values[key]
        if self.values.get('ai_provider') not in ('offline', 'custom', 'ollama', 'groq'):
            self.values['ai_provider'] = 'custom'
        if not isinstance(self.values.get('provider_profiles'), dict):
            self.values['provider_profiles'] = {}
        for key, minimum, maximum in (('ai_max_tokens', 32, 4096), ('ai_daily_limit', 0, 10000)):
            try:
                self.values[key] = min(maximum, max(minimum, int(self.values[key])))
            except (ValueError, TypeError):
                self.values[key] = DEFAULTS[key]
        try:
            self.values['ai_temperature'] = min(2, max(0, float(self.values['ai_temperature'])))
        except (ValueError, TypeError):
            self.values['ai_temperature'] = .7

    def get(self, key):
        return self.values.get(key)

    def update(self, **values):
        self.values.update(values)
        self.directory.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
        os.replace(temp, self.path)


def startup_enabled():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
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
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "BiscuitCompanion", 0, winreg.REG_SZ, subprocess.list2cmdline(args))
        else:
            try:
                winreg.DeleteValue(key, "BiscuitCompanion")
            except FileNotFoundError:
                pass
