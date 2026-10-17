"""Preload standalone sprites and grid atlases; no image processing in paintEvent."""
import json
from pathlib import Path
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QBitmap, QPainter, QPixmap, QRegion

ASSETS = Path(__file__).resolve().parent / "assets"


class SpriteBank:
    def __init__(self, directory=ASSETS):
        self.directory = Path(directory).resolve()
        self.manifest = json.loads((self.directory / "sprites.json").read_text(encoding="utf-8"))
        self.images = {}
        self.atlases = {}
        for name, spec in self.manifest.get("atlases", {}).items():
            self._load_atlas(name, spec)
        self.states = self.manifest["states"]
        for state in self.states.values():
            if not state["frames"] or not 0 < state["fps"] <= 60:
                raise ValueError("Each sprite state needs frames and an fps between 0 and 60.")
            for frames in [state["frames"], *state.get("directions", {}).values()]:
                if not frames or len(frames) != len(state["frames"]):
                    raise ValueError("All directions in a state need the same nonzero frame count.")
                for frame in frames:
                    self._load_frame(frame)

    def _path(self, name):
        path = (self.directory / name).resolve()
        if not path.is_relative_to(self.directory):
            raise ValueError("Sprite paths must stay inside the asset directory.")
        return path

    def _read(self, name):
        pixmap = QPixmap(str(self._path(name)))
        if pixmap.isNull():
            raise ValueError(f"Missing or invalid pet sprite: {name}")
        return pixmap

    def _load_atlas(self, name, spec):
        sheet = self._read(spec["file"])
        cols, rows = spec["columns"], spec["rows"]
        if not isinstance(cols, int) or not isinstance(rows, int) or not 1 <= cols <= 32 or not 1 <= rows <= 32:
            raise ValueError("Sprite atlas grid dimensions must be integers between 1 and 32.")
        if sheet.width() < cols or sheet.height() < rows:
            raise ValueError("Sprite atlas cells cannot be empty.")
        edges = spec.get("row_edges", [i / rows for i in range(rows + 1)])
        if (len(edges) != rows + 1 or edges[0] != 0 or edges[-1] != 1
                or any(a >= b for a, b in zip(edges, edges[1:]))):
            raise ValueError("Atlas row_edges must increase from 0 to 1 and describe every row.")
        columns = spec.get("column_edges", [i / cols for i in range(cols + 1)])
        if (len(columns) != cols + 1 or columns[0] != 0 or columns[-1] != 1
                or any(a >= b for a, b in zip(columns, columns[1:]))):
            raise ValueError("Atlas column_edges must increase from 0 to 1 and describe every column.")
        cells = {}
        # Integer boundaries also handle image sizes not divisible by the grid.
        for row in range(rows):
            for col in range(cols):
                left, right = round(columns[col] * sheet.width()), round(columns[col + 1] * sheet.width())
                top, bottom = round(edges[row] * sheet.height()), round(edges[row + 1] * sheet.height())
                cell = sheet.copy(left, top, right - left, bottom - top)
                alpha = cell.toImage().createAlphaMask(Qt.ThresholdAlphaDither)
                bounds = QRegion(QBitmap.fromImage(alpha)).boundingRect()
                if bounds.isEmpty():
                    raise ValueError(f"Empty sprite in atlas {name}, cell {col},{row}.")
                cells[col, row] = cell, bounds
        # One scale preserves proportions. Bottom-center anchors remove small
        # placement differences in the sheet without resizing individual frames.
        scale = min(432 / max(bounds.height() for _, bounds in cells.values()),
                    446 / max(bounds.width() for _, bounds in cells.values()))
        normalized = {}
        for (col, row), (cell, bounds) in cells.items():
            canvas = QPixmap(480, 480)
            canvas.fill(Qt.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            x = 240 - (bounds.x() + bounds.width() / 2) * scale
            y = 461 - (bounds.y() + bounds.height()) * scale
            painter.drawPixmap(QRectF(x, y, cell.width() * scale, cell.height() * scale), cell, QRectF(cell.rect()))
            painter.end()
            normalized[col, row] = canvas
        self.atlases[name] = normalized

    @staticmethod
    def _key(frame):
        if isinstance(frame, str):
            return frame
        if isinstance(frame, dict) and set(frame) == {"atlas", "column", "row"}:
            return frame["atlas"], frame["column"], frame["row"]
        raise ValueError("A frame must be a PNG filename or an atlas/column/row object.")

    def _load_frame(self, frame):
        key = self._key(frame)
        if key not in self.images:
            if isinstance(key, str):
                self.images[key] = self._read(key).scaled(480, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                atlas, col, row = key
                if not isinstance(col, int) or not isinstance(row, int) or atlas not in self.atlases or (col, row) not in self.atlases[atlas]:
                    raise ValueError(f"Invalid sprite atlas cell: {atlas}, {col}, {row}.")
                self.images[key] = self.atlases[atlas][col, row]

    def spec(self, state):
        return self.states.get(state, self.states["idle"])

    def frame(self, state, elapsed, facing="front"):
        spec = self.spec(state)
        frames = spec.get("directions", {}).get(facing, spec["frames"])
        frame = frames[int(max(0, elapsed) * spec["fps"]) % len(frames)]
        return self.images[self._key(frame)]

    def eyes(self, state):
        return self.spec(state).get("eyes", self.manifest.get("eyes", []))
