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
    path.write_text('{"scale":"bad", "wander":"false", "x":{}, "name":null, "api_key":"bad"}')
    restored = Settings(tmp_path)
    assert restored.get("scale") == 100
    assert restored.get("wander") is False
    assert restored.get("x") is None
    assert restored.get("name") == "Biscuit"
    assert restored.get("api_key") is None
    path.write_text("broken json")
    assert Settings(tmp_path).get("scale") == 100
