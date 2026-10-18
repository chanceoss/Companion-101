"""Render activity poses using the same native painter as the desktop window."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from desktop_pet.activities import ACTIVITIES
from desktop_pet.pet import PetWindow
from desktop_pet.sprites import SpriteBank
from desktop_pet.storage import Settings


def main():
    app = QApplication.instance() or QApplication([])
    output = Path(__file__).resolve().parent.parent / "docs" / "activities.gif"
    with TemporaryDirectory() as directory:
        pet = PetWindow(Settings(directory), SpriteBank())
        pet.timer.stop()
        pet.set_scale(65)
        pet.show()
        frames = []
        for index in range(8):
            stage = QPixmap(pet.width() * 5, pet.height() + 32)
            stage.fill(QColor("#faf8f3"))
            painter = QPainter(stage)
            painter.setFont(QFont("Segoe UI", 10))
            painter.setPen(QColor("#77614d"))
            for col, activity in enumerate(ACTIVITIES):
                pet.set_state("idle", transition=False)
                pet.set_state(activity.scene, transition=False)
                pet.pose = pet.animator.advance(index / 8)
                painter.drawPixmap(col * pet.width(), 0, pet.grab())
                painter.drawText(col * pet.width(), stage.height() - 30, pet.width(), 25,
                                 Qt.AlignCenter, activity.title)
            painter.end()
            image = stage.toImage().convertToFormat(QImage.Format_RGBA8888)
            frames.append(Image.frombytes("RGBA", (image.width(), image.height()), bytes(image.bits())).convert("RGB"))
        output.parent.mkdir(exist_ok=True)
        frames[0].save(output, save_all=True, append_images=frames[1:], duration=125, loop=0, disposal=2)
        pet.hide()
        pet.bubble.hide()
        print(output)


if __name__ == "__main__":
    main()
