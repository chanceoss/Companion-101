import argparse
import math
from pathlib import Path
import sys
import time
from PySide6.QtCore import Qt, QTimer, QStandardPaths, QLockFile
from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon
from .ai import Companion
from .panel import ControlPanel
from .pet import PetWindow
from .sprites import SpriteBank, ASSETS
from .storage import Settings


class Application:
    def __init__(self, app, settings=None, show_panel=True):
        self.app = app
        self._cleaned = False
        self.settings = settings or Settings()
        self.sprites = SpriteBank()
        self.companion = Companion(self.settings, app)
        self.companion.load_key()
        self.pet = PetWindow(self.settings, self.sprites)
        self.panel = ControlPanel(self.settings, self.sprites, self.companion)
        self.icon = QIcon(str(ASSETS / "biscuit.png"))
        app.setWindowIcon(self.icon)
        self.panel.setWindowIcon(self.icon)
        self.tray = QSystemTrayIcon(self.icon, app)
        self.tray.setToolTip("Biscuit · Your desktop companion")
        self.menu = QMenu()
        self.action("Open companion", lambda: self.panel.open())
        self.action("Let’s chat", lambda: self.panel.open(chat=True))
        self.action("Bring pet back", self.summon)
        self.menu.addSeparator()
        self.wander = self.action("Explore desktop", self.set_wander, checkable=True)
        self.wander.setChecked(self.settings.get("wander"))
        self.sleep_action = self.action("Take a nap / wake up", self.toggle_sleep)
        self.pass_through = self.action("Click through pet", self.set_click_through, checkable=True)
        self.action("Hide pet", self.hide_pet)
        self.menu.addSeparator()
        self.action("Quit Biscuit", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_clicked)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            # Without a tray, never allow an unrecoverable hidden or click-through pet.
            for action in (self.pass_through,):
                action.setEnabled(False)
        self.pet.open_requested.connect(lambda: self.panel.open(chat=True))
        self.pet.menu_requested.connect(lambda point: self.menu.popup(point))
        self.pet.position_saved.connect(self.save_position)
        self.pet.state_changed.connect(self.panel.set_state)
        self.pet.hidden_to_tray.connect(self.on_hidden)
        self.panel.summon_requested.connect(self.summon)
        self.panel.pet_requested.connect(self.show_love)
        self.panel.sleep_requested.connect(self.toggle_sleep)
        self.panel.wander_changed.connect(self.set_wander)
        self.panel.scale_changed.connect(self.set_scale)
        self.panel.message_sent.connect(self.companion.send)
        self.panel.clear_requested.connect(self.companion.clear)
        self.panel.quit_requested.connect(self.quit)
        self.panel.focus_requested.connect(self.toggle_focus)
        self.companion.answered.connect(self.answer)
        self.companion.failed.connect(lambda message: self.panel.add_message("Connection", message, error=True))
        self.companion.busy_changed.connect(self.panel.set_busy)
        self.focus_deadline = None
        self.focus_timer = QTimer(app)
        self.focus_timer.timeout.connect(self.focus_tick)
        self.focus_timer.start(1000)
        app.screenRemoved.connect(lambda _: QTimer.singleShot(100, self.pet.restore_position))
        app.aboutToQuit.connect(self.cleanup)
        self.pet.show()
        if show_panel:
            self.panel.show()
        self.hello_timer = QTimer(self.pet)
        self.hello_timer.setSingleShot(True)
        self.hello_timer.timeout.connect(lambda: self.pet.say("Hi, I’m Biscuit! Drag me anywhere. Double-click to chat. 🐾"))
        self.hello_timer.start(800)

    def action(self, title, callback, checkable=False):
        action = QAction(title, self.menu)
        action.setCheckable(checkable)
        action.triggered.connect(callback)
        self.menu.addAction(action)
        return action

    def tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.panel.open()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.summon()

    def summon(self):
        self.pass_through.setChecked(False)
        self.pet.summon()

    def hide_pet(self):
        self.pet.hide_animated()

    def on_hidden(self):
        if not self.tray.isVisible():
            self.panel.open()

    def show_love(self):
        if not self.pet.isVisible():
            self.summon()
        self.pet.pet()

    def toggle_sleep(self):
        if not self.pet.isVisible():
            self.summon()
        self.pet.sleep(self.pet.animator.state != "sleeping")

    def set_wander(self, enabled):
        self.settings.update(wander=enabled)
        self.wander.blockSignals(True)
        self.wander.setChecked(enabled)
        self.wander.blockSignals(False)
        self.panel.wander.blockSignals(True)
        self.panel.wander.setChecked(enabled)
        self.panel.wander.blockSignals(False)

    def set_scale(self, scale):
        self.pet.set_scale(scale)
        self.settings.update(scale=scale)

    def set_click_through(self, enabled):
        self.pet.set_click_through(enabled)
        if enabled:
            self.tray.showMessage("Biscuit is click-through", "Use the tray menu → Bring pet back to interact again.", QSystemTrayIcon.Information, 5000)

    def save_position(self, x, y):
        self.settings.update(x=x, y=y)

    def answer(self, message):
        self.panel.add_message(self.settings.get("name"), message)
        self.pet.say(message)
        if self.pet.animator.state != "sleeping":
            self.pet.set_state("happy")

    def toggle_focus(self):
        if self.focus_deadline:
            self.focus_deadline = None
            self.panel.focus.setText("◷  Focus together · 25 min")
            self.pet.say("Focus session paused. We can start fresh anytime.")
        else:
            self.focus_deadline = time.monotonic() + 25 * 60
            self.pet.say("One small task. Twenty-five cozy minutes. Let’s do this!")
            self.focus_tick()

    def focus_tick(self):
        if self.focus_deadline is None:
            return
        remaining = max(0, math.ceil(self.focus_deadline - time.monotonic()))
        self.panel.focus.setText(f"◷  {remaining // 60:02d}:{remaining % 60:02d} · Stop")
        if remaining == 0:
            self.focus_deadline = None
            self.panel.focus.setText("◷  Focus together · 25 min")
            message = "You did it! Time for a stretch and a tiny celebration."
            self.pet.say(message)
            if self.pet.animator.state != "sleeping":
                self.pet.set_state("happy")
            if self.tray.isVisible():
                self.tray.showMessage("Focus complete", message)
            self.panel.add_message(self.settings.get("name"), message)

    def cleanup(self):
        if self._cleaned:
            return
        self._cleaned = True
        self.save_position(self.pet.x(), self.pet.y())
        self.hello_timer.stop()
        self.focus_timer.stop()
        self.companion.shutdown()
        self.pet.timer.stop()
        self.pet.bubble.hide()
        self.tray.hide()

    def quit(self):
        self.pet.allow_close = True
        self.panel.allow_close = True
        self.pet.bubble.close()
        self.app.quit()


def main():
    parser = argparse.ArgumentParser(description="Biscuit desktop companion")
    parser.add_argument("--startup", action="store_true", help="Start pet without opening the control panel")
    parser.add_argument("--smoke-test", action="store_true", help="Render the native windows and exit after two seconds")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("BiscuitCompanion")
    app.setOrganizationName("Companion101")
    app.setQuitOnLastWindowClosed(False)
    directory = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
    directory.mkdir(parents=True, exist_ok=True)
    # Local IPC only. Avoid two copies of an always-on-top companion.
    socket_name = "BiscuitCompanion-" + __import__("hashlib").sha256(str(directory).encode()).hexdigest()[:16]
    server = QLocalServer(app)
    lock = QLockFile(str(directory / "instance.lock"))
    lock.setStaleLockTime(0)
    if not args.smoke_test:
        if not lock.tryLock(100):
            socket = QLocalSocket()
            socket.connectToServer(socket_name)
            if socket.waitForConnected(1500):
                socket.write(b"show")
                socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
            else:
                QMessageBox.information(None, "Biscuit", "Biscuit is already running. Find the pet or its icon in the system tray.")
            return 0
        QLocalServer.removeServer(socket_name)
        server.setSocketOptions(QLocalServer.UserAccessOption)
        if not server.listen(socket_name):
            lock.unlock()
            QMessageBox.critical(None, "Biscuit", "Could not open the local companion channel. Try starting the app again.")
            return 1
    try:
        controller = Application(app, show_panel=not args.startup)
    except (OSError, ValueError, KeyError) as exc:
        QMessageBox.critical(None, "Biscuit could not start", str(exc))
        return 1

    def activate_existing():
        connection = server.nextPendingConnection()
        if connection:
            controller.summon()
            controller.panel.open()
            connection.disconnectFromServer()
            connection.deleteLater()

    server.newConnection.connect(activate_existing)
    if args.smoke_test:
        QTimer.singleShot(2000, controller.quit)
    result = app.exec()
    server.close()
    if lock.isLocked():
        lock.unlock()
    return result
