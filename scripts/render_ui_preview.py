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
        controller.panel.resize(1040, 1100)

        def capture_main():
            controller.panel.grab().save(str(output / "companion.png"))
            controller.panel.open_preferences()
            QTimer.singleShot(100, capture_preferences)

        def capture_preferences():
            controller.panel.preferences.grab().save(str(output / "preferences.png"))
            controller.quit()

        QTimer.singleShot(250, capture_main)
        code = app.exec()
    print(output / "companion.png")
    print(output / "preferences.png")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
