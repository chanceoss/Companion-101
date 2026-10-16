import json
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

ASSETS = Path(__file__).resolve().parent / "assets"


class SpriteBank:
    def __init__(self, directory=ASSETS):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "sprites.json").read_text(encoding="utf-8"))
        self.images = {}
        for state in self.manifest["states"].values():
            if not state["frames"] or not 0 < state["fps"] <= 60:
                raise ValueError("Each sprite state needs frames and an fps between 0 and 60.")
            for name in state["frames"]:
                path = (self.directory / name).resolve()
                if not path.is_relative_to(self.directory.resolve()):
                    raise ValueError("Sprite paths must stay inside the asset directory.")
                if name not in self.images:
                    pixmap = QPixmap(str(path))
                    if pixmap.isNull():
                        raise ValueError(f"Missing or invalid pet sprite: {name}")
                    self.images[name] = pixmap.scaled(480, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def frame(self, state, elapsed):
        spec = self.manifest["states"].get(state, self.manifest["states"]["idle"])
        return self.images[spec["frames"][int(elapsed * spec["fps"]) % len(spec["frames"])]]
