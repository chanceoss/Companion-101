import json
from desktop_pet.storage import Settings


def test_preferences_round_trip_excludes_unknown_keys(tmp_path, app):
    settings = Settings(tmp_path)
    settings.update(scale=120, wander=True, x=-500, y=400)
    restored = Settings(tmp_path)
    assert restored.get("scale") == 120
    assert restored.get("x") == -500
    assert restored.get("wander") is True
    assert "key" not in json.loads(restored.path.read_text())


def test_corrupt_and_malformed_preferences_recover(tmp_path, app):
    path = tmp_path / "settings.json"
    path.write_text(
        '{"scale":"bad", "wander":"false", "x":{}, "name":null, "api_key":"bad"}'
    )
    restored = Settings(tmp_path)
    assert restored.get("scale") == 100
    assert restored.get("wander") is False
    assert restored.get("x") is None
    assert restored.get("name") == "Biscuit"
    assert restored.get("api_key") is None
    path.write_text("broken json")
    assert Settings(tmp_path).get("scale") == 100


def test_optional_settings_recover_and_credentials_never_enter_json(tmp_path, app):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "weather_enabled": True,
                "weather_latitude": [],
                "weather_longitude": float("inf"),
                "weather_interval": "bad",
                "voice_speed": float("nan"),
                "voice_volume": {},
                "voice_python": [],
                "voice_mode": "continuous",
                "provider_profiles": {
                    "custom": {
                        "endpoint": "https://example.test/v1",
                        "model": "test",
                        "api_key": "secret",
                    },
                    "bad": {},
                },
                "ai_usage": ["bad"],
                "trivia_total": "bad",
                "trivia_correct": 999,
                "calendar_reminder_minutes": -5,
            }
        )
    )
    settings = Settings(tmp_path)
    assert (
        settings.get("weather_enabled") is False
        and settings.get("weather_interval") == 30
    )
    assert (
        settings.get("voice_speed") == 1
        and settings.get("voice_volume") == 70
        and settings.get("voice_python") == ""
    )
    assert settings.get("voice_mode") == "text" and settings.get("trivia_correct") == 0
    assert settings.get("provider_profiles") == {
        "custom": {"endpoint": "https://example.test/v1", "model": "test"}
    }
    settings.update(api_key="do-not-store", refresh_token="do-not-store")
    assert "secret" not in path.read_text() and "do-not-store" not in path.read_text()


def test_failed_atomic_save_preserves_in_memory_and_disk_settings(
    tmp_path, app, monkeypatch
):
    import os
    import pytest

    settings = Settings(tmp_path)
    settings.update(name="Before")
    previous = settings.path.read_bytes()
    monkeypatch.setattr(
        os, "replace", lambda *args: (_ for _ in ()).throw(PermissionError("Read only"))
    )
    with pytest.raises(OSError):
        settings.update(name="After")
    assert settings.get("name") == "Before" and settings.path.read_bytes() == previous


def test_invalid_saved_timezone_recovers_without_preventing_startup(tmp_path, app):
    (tmp_path / "settings.json").write_text(
        json.dumps({"reminder_timezone": "Not/A_Zone"})
    )
    assert Settings(tmp_path).get("reminder_timezone") == ""
