"""Export classic or conversation reactions from the actual native pet painter."""

import argparse
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from desktop_pet.avatars import AVATARS, avatar_spec
from desktop_pet.gestures import CLASSIC_GESTURES, CONVERSATION_GESTURES
from desktop_pet.pet import PetWindow
from desktop_pet.sprites import SpriteBank
from desktop_pet.storage import Settings
from desktop_pet.theme import load_fonts, ui_font


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversation", action="store_true")
    parser.add_argument("--avatar", choices=AVATARS, default="biscuit")
    args = parser.parse_args()
    gestures = CONVERSATION_GESTURES if args.conversation else CLASSIC_GESTURES
    app = QApplication.instance() or QApplication([])
    load_fonts()
    output = (
        Path(__file__).resolve().parent.parent
        / "docs"
        / ("conversation-expressions.gif" if args.conversation else "expressions.gif")
    )
    if args.avatar != "biscuit":
        output = output.with_name(args.avatar + "-" + output.name)
    with TemporaryDirectory() as directory:
        sprites = SpriteBank(avatar=args.avatar)
        gestures = [(state, sprites.spec(state).get("menu_label", title)) for state, title in gestures]
        pets = []
        for state, title in gestures:
            pet = PetWindow(Settings(Path(directory) / state), sprites)
            pet.timer.stop()
            pet.set_scale(70)
            pet.set_state("idle", transition=False)
            pet.pose = pet.animator.advance(0)
            pet.show()
            pets.append(pet)
        app.processEvents()
        cell_width, cell_height = pets[0].width() + 16, pets[0].height() + 44
        frames = []
        for index in range(48):
            stage = QPixmap(cell_width * 3, cell_height * 2 + 50)
            stage.fill(QColor("#fcf8f2"))
            painter = QPainter(stage)
            painter.setRenderHints(
                QPainter.Antialiasing | QPainter.SmoothPixmapTransform
            )
            painter.setPen(QColor("#593b2c"))
            painter.setFont(ui_font(23, 600, heading=True))
            painter.drawText(
                QRectF(12, 5, stage.width() - 24, 36),
                Qt.AlignCenter,
                "Small paws. Big feelings."
                if args.conversation
                else f"A little more {avatar_spec(args.avatar).name}.",
            )
            for cell, ((state, title), pet) in enumerate(zip(gestures, pets)):
                if index == 3:
                    pet.set_state(state, restart=True)
                pet.pose = pet.animator.advance(0.1 if index else 0)
                x, y = (cell % 3) * cell_width, (cell // 3) * cell_height + 50
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#f3eddf"))
                painter.drawRoundedRect(
                    QRectF(x + 5, y + 2, cell_width - 10, cell_height - 6), 22, 22
                )
                painter.drawPixmap(x + 8, y + 5, pet.grab())
                painter.setPen(QColor("#876548"))
                painter.setFont(ui_font(17, 700))
                painter.drawText(
                    QRectF(x + 5, y + cell_height - 36, cell_width - 10, 26),
                    Qt.AlignCenter,
                    title,
                )
            painter.end()
            picture = stage.toImage().convertToFormat(QImage.Format_RGBA8888)
            frames.append(
                Image.frombytes(
                    "RGBA", (picture.width(), picture.height()), bytes(picture.bits())
                ).convert("RGB")
            )
        output.parent.mkdir(exist_ok=True)
        frames[0].save(
            output,
            save_all=True,
            append_images=frames[1:],
            duration=100,
            loop=0,
            disposal=2,
        )
        if args.conversation:
            frames[16].save(output.with_suffix(".png"))
        for pet in pets:
            pet.hide()
            pet.bubble.hide()
            pet.deleteLater()
    print(output)


if __name__ == "__main__":
    main()
