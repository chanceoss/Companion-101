"""Capture the real native panel and its gear-opened Preferences window."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from desktop_pet.app import Application
from desktop_pet.storage import Settings


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    output = Path(__file__).resolve().parent.parent / "docs"
    output.mkdir(exist_ok=True)
    with TemporaryDirectory() as directory:
        controller = Application(app, Settings(directory))
        controller.hello_timer.stop()
        controller.pet.timer.stop()
        controller.pet.hide()
        controller.panel.portrait.animator.set_state("idle", transition=False)
        controller.panel.portrait.pose = controller.panel.portrait.animator.advance(0)
        controller.panel.portrait.timer.stop()
        controller.panel.resize(1040, 1100)

        def capture_main():
            controller.panel.grab().save(str(output / "companion.png"))
            controller.panel.resize(480, 540)
            QTimer.singleShot(100, capture_compact)

        def capture_compact():
            controller.panel.grab().save(str(output / "compact.png"))
            controller.panel.open_preferences()
            QTimer.singleShot(100, capture_preferences)

        def capture_preferences():
            controller.panel.preferences.grab().save(str(output / "preferences.png"))
            controller.panel.preferences.section_nav.setCurrentIndex(4)
            QTimer.singleShot(100, capture_voice)

        def capture_voice():
            controller.panel.preferences.grab().save(
                str(output / "preferences-voice.png")
            )
            controller.panel.preferences.hide()
            controller.tools.open_page("trivia")
            controller.trivia.next("medium", daily=True)
            QTimer.singleShot(100, capture_tools)

        def capture_tools():
            controller.tools.grab().save(str(output / "tools.png"))
            controller.quit()

        QTimer.singleShot(250, capture_main)
        code = app.exec()
    print(output / "companion.png")
    print(output / "compact.png")
    print(output / "preferences.png")
    print(output / "preferences-voice.png")
    print(output / "tools.png")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
