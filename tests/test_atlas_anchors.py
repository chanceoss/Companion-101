"""Changing tail silhouettes must not move the character's torso between frames."""
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from desktop_pet.sprites import SpriteBank


def make_atlas(directory, anchors=None):
    # Identical blue torsos share the same local center. Only the isolated red
    # tails change sides, making each silhouette's bounding-box center differ.
    sheet = QImage(200, 100, QImage.Format_ARGB32_Premultiplied)
    sheet.fill(Qt.transparent)
    painter = QPainter(sheet)
    painter.fillRect(40, 30, 20, 60, QColor("blue"))
    painter.fillRect(140, 30, 20, 60, QColor("blue"))
    painter.fillRect(10, 50, 20, 20, QColor("red"))
    painter.fillRect(170, 50, 20, 20, QColor("red"))
    painter.end()
    assert sheet.save(str(directory / "synthetic.png"))
    atlas = {"file": "synthetic.png", "columns": 2, "rows": 1}
    if anchors is not None:
        atlas["column_anchors"] = anchors
    manifest = {
        "atlases": {"synthetic": atlas},
        "states": {"idle": {"frames": [
            {"atlas": "synthetic", "column": column, "row": 0} for column in range(2)
        ]}},
    }
    (directory / "sprites.json").write_text(json.dumps(manifest))


def blue_body_center(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    data = image.constBits()
    positions = [index // 4 % image.width() for index in range(0, image.sizeInBytes(), 4)
                 if data[index] < 50 and data[index + 1] < 50
                 and data[index + 2] > 200 and data[index + 3] > 200]
    assert positions
    return (min(positions) + max(positions)) / 2


def test_explicit_source_anchors_keep_torso_aligned_despite_tail_silhouette_changes(app, tmp_path):
    make_atlas(tmp_path, [.25, .75])
    sprites = SpriteBank(tmp_path)
    centers = [blue_body_center(sprites.atlases["synthetic"][column, 0]) for column in range(2)]
    assert centers[0] == pytest.approx(centers[1], abs=1)
    assert centers[0] == pytest.approx(240, abs=1)

    # Legacy atlases still use silhouette centering when no anchors are given.
    make_atlas(tmp_path)
    legacy = SpriteBank(tmp_path)
    legacy_centers = [blue_body_center(legacy.atlases["synthetic"][column, 0]) for column in range(2)]
    assert abs(legacy_centers[0] - legacy_centers[1]) > 100


@pytest.mark.parametrize("anchors", [
    pytest.param([.25], id="wrong-count"),
    pytest.param([float("nan"), .75], id="not-finite"),
    pytest.param([-.1, .75], id="outside-first-cell"),
    pytest.param([.25, .25], id="outside-second-cell"),
    pytest.param(".25,.75", id="string-instead-of-list"),
    pytest.param([".25", .75], id="string-coordinate"),
    pytest.param([True, .75], id="boolean-coordinate"),
])
def test_invalid_source_anchors_are_rejected_as_configuration_errors(app, tmp_path, anchors):
    make_atlas(tmp_path, anchors)
    with pytest.raises(ValueError):
        SpriteBank(tmp_path)
