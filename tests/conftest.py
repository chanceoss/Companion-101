import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/biscuit-test-cache" if os.name != "nt" else os.environ.get("TEMP", "."))
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def app():
    instance = QApplication.instance() or QApplication([])
    instance.setApplicationName("BiscuitTest")
    instance.setQuitOnLastWindowClosed(False)
    return instance
