"""Export actual Qt pet rendering: python -m scripts.render_walk_preview (dev deps)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from desktop_pet.model import WalkMotion
from desktop_pet.pet import PetWindow
from desktop_pet.sprites import SpriteBank
from desktop_pet.storage import Settings


def main():
    app = QApplication.instance() or QApplication([])
    sprites = SpriteBank()
    output = Path(__file__).resolve().parent.parent / "docs" / "walking.gif"
    with TemporaryDirectory() as directory:
        pet = PetWindow(Settings(directory), sprites)
        pet.timer.stop()
        pet.set_scale(80)
        pet.show()
        frames = []
        spec = sprites.spec("walking")
        for index in range(len(spec["frames"])):
            stage = QPixmap(pet.width() * 4, pet.height() + 45)
            stage.fill(QColor("#faf8f3"))
            painter = QPainter(stage)
            painter.setFont(QFont("Segoe UI", 11))
            painter.setPen(QColor("#77614d"))
            for col, (title, vector) in enumerate((("Walking down", (0, 1)), ("Walking right", (1, 0)),
                                                    ("Walking left", (-1, 0)), ("Walking up", (0, -1)))):
                pet.set_state("idle", transition=False)
                pet.set_state("walking", transition=False)
                pet.walk_motion = WalkMotion(0, 0, *vector)
                pet.direction = -1 if vector[0] < 0 else 1
                pet.pose = pet.animator.advance(index / spec["fps"])
                painter.drawPixmap(col * pet.width(), 15, pet.grab())
                painter.drawText(col * pet.width(), stage.height() - 30, pet.width(), 25, Qt.AlignCenter, title)
            painter.end()
            image = stage.toImage().convertToFormat(QImage.Format_RGBA8888)
            frames.append(Image.frombytes("RGBA", (image.width(), image.height()), bytes(image.bits())).convert("RGB"))
        output.parent.mkdir(exist_ok=True)
        frames[0].save(output, save_all=True, append_images=frames[1:],
                       duration=round(1000 / spec["fps"]), loop=0, disposal=2)
        pet.hide()
        pet.bubble.hide()
        print(output)


if __name__ == "__main__":
    main()
