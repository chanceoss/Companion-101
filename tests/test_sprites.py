import json
import shutil
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QBitmap, QRegion
from desktop_pet.sprites import SpriteBank, ASSETS


def test_directional_cycle_uses_distinct_frames_and_loops(app):
    sprites = SpriteBank()
    keys = []
    for facing in ("front", "side", "back"):
        frames = [sprites.frame("walking", i / 8, facing) for i in range(4)]
        assert len({f.cacheKey() for f in frames}) == 4
        assert sprites.frame("walking", .5, facing).cacheKey() == frames[0].cacheKey()
        keys.extend(f.cacheKey() for f in frames)
        for frame in frames:
            image = frame.toImage()
            assert image.hasAlphaChannel()
            assert image.pixelColor(0, 0).alpha() == 0
            alpha = image.createAlphaMask(Qt.ThresholdAlphaDither)
            bounds = QRegion(QBitmap.fromImage(alpha)).boundingRect()
            assert bounds.top() >= 5
            assert bounds.bottom() <= 465
    assert len(set(keys)) == 12
    assert sprites.eyes("walking") == []  # Front idle eyelids never cover side/back views.
    assert len(sprites.eyes("idle")) == 2
    assert sprites.frame("unknown", 0).cacheKey() == sprites.frame("idle", 0).cacheKey()


@pytest.mark.parametrize("broken", ["cell", "direction", "row_edges", "column_edges", "path"])
def test_bad_sprite_configuration_reports_actionable_error(app, tmp_path, broken):
    config = json.loads((ASSETS / "sprites.json").read_text())
    for path in ASSETS.glob("*.png"):
        shutil.copyfile(path, tmp_path / path.name)
    if broken == "cell":
        config["states"]["walking"]["frames"][0]["column"] = 100
        expected = "Invalid sprite atlas cell"
    elif broken == "direction":
        config["states"]["walking"]["directions"]["side"].pop()
        expected = "same nonzero frame count"
    elif broken == "row_edges":
        config["atlases"]["walk"]["row_edges"] = [0, .6, .5, 1]
        expected = "row_edges"
    elif broken == "column_edges":
        config["atlases"]["activities"]["column_edges"] = [0, .9, .8, .7, .6, 1]
        expected = "column_edges"
    else:
        config["atlases"]["walk"]["file"] = "../outside.png"
        expected = "inside the asset directory"
    (tmp_path / "sprites.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match=expected):
        SpriteBank(tmp_path)


def test_activity_art_has_five_distinct_transparent_scenes(app):
    sprites = SpriteBank()
    scenes = ("exploring", "working", "greeting", "sleeping", "following")
    assert len({sprites.frame(scene, 0).cacheKey() for scene in scenes}) == 5
    for scene in scenes:
        frame = sprites.frame(scene, 0).toImage()
        assert frame.hasAlphaChannel()
        assert frame.pixelColor(0, 0).alpha() == 0
        assert sprites.eyes(scene) == []
