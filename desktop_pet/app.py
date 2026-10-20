import argparse
import math
import re
import sqlite3
from pathlib import Path
import sys
import time
from PySide6.QtCore import Qt, QTimer, QStandardPaths, QLockFile
from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QFileDialog
from .ai import Companion
from .panel import ControlPanel
from .pet import PetWindow
from .sprites import SpriteBank, ASSETS
from .storage import Settings
from .gestures import GESTURES
from .services.weather import WeatherService
from .services.system_monitor import SystemMonitor
from .tools import ToolsDialog
from .services.voice import VoiceService
from .services.speech_recognition import SpeechRecognition
from .services.reminders import ReminderService
from .services.google import GoogleServices
from .services.calendar import schedule_summary


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
        self.weather = WeatherService(self.settings)
        self.system_monitor = SystemMonitor(self.settings)
        self.voice = VoiceService(self.settings)
        self.recognition = SpeechRecognition(self.settings)
        self.reminders = ReminderService(self.settings)
        self.google = GoogleServices(self.settings, self.reminders.store)
        self._pending_notices = []
        self._calendar_reply = False
        self.tools = ToolsDialog(self.settings, self.weather, self.system_monitor, self.panel)
        self.panel.tools_requested.connect(self.tools.open_page)
        self.panel.preferences_saved.connect(self.apply_services)
        self.tools.location_chosen.connect(self.choose_location)
        self.weather.updated.connect(self.weather_reaction)
        self.system_monitor.notification.connect(self.ambient_notice)
        self.tools.add_voice(self.voice, self.recognition)
        self.tools.add_productivity(self.reminders, self.google, self.connect_google)
        self.panel.add_tool('voice', 'Voice')
        for key, title in (('reminders','Reminders'),('tasks','Tasks'),('google','Google / Calendar')):
            self.panel.add_tool(key, title)
        self.reminders.due_reminder.connect(self.deliver_reminder)
        self.google.due_event.connect(self.deliver_calendar_event)
        self.google.events_loaded.connect(self.calendar_received)
        self.google.connection_changed.connect(self.google_connection_changed)
        self.google.status.connect(self.google_status)
        self.panel.microphone_requested.connect(self.recognition.toggle)
        self.recognition.listening.connect(self.panel.set_listening)
        self.recognition.status.connect(self.panel.set_voice_status)
        self.recognition.transcribed.connect(self.review_transcription)
        self.voice.status.connect(self.panel.set_voice_status)
        self.voice.speaking.connect(self.speech_reaction)
        self.voice.downloaded.connect(self.model_downloaded)
        self.panel.mute_requested.connect(self.set_muted)
        self.panel.preferences.features.download_requested.connect(self.download_model)
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
        self.work_action = self.action("Work with me · 25 min", lambda: self.activate_activity("work"), checkable=True)
        self.action("Say hi", lambda: self.activate_activity("greet"))
        self.sleep_action = self.action("Take a nap / wake up", self.toggle_sleep)
        self.follow_action = self.action("Follow me", lambda: self.activate_activity("follow"), checkable=True)
        self.action("Rest here / stop activity", lambda: self.activate_activity("idle"))
        self.gesture_menu = self.menu.addMenu("Biscuit reactions")
        self.gesture_actions = {}
        for state, title in GESTURES:
            action = self.gesture_menu.addAction(title)
            action.triggered.connect(lambda checked=False, key=state: self.perform_gesture(key))
            self.gesture_actions[state] = action
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
        self.pet.activity_changed.connect(self.sync_activity)
        self.pet.hidden_to_tray.connect(self.on_hidden)
        self.panel.summon_requested.connect(self.summon)
        self.panel.pet_requested.connect(self.show_love)
        self.panel.sleep_requested.connect(self.toggle_sleep)
        self.panel.scale_changed.connect(self.set_scale)
        self.panel.message_sent.connect(self.handle_message)
        self.panel.clear_requested.connect(self.companion.clear)
        self.panel.quit_requested.connect(self.quit)
        self.panel.focus_requested.connect(self.toggle_focus)
        self.panel.activity_requested.connect(self.activate_activity)
        self.panel.gesture_requested.connect(self.perform_gesture)
        self.companion.answered.connect(self.answer)
        self.companion.failed.connect(lambda message: self.panel.add_message("Connection", message, error=True))
        self.companion.busy_changed.connect(self.panel.set_busy)
        self.focus_deadline = None
        self.focus_timer = QTimer(app)
        self.focus_timer.timeout.connect(self.focus_tick)
        self.focus_timer.start(1000)
        self.sync_activity(self.pet.activity)
        app.screenRemoved.connect(lambda _: QTimer.singleShot(100, self.pet.restore_position))
        app.aboutToQuit.connect(self.cleanup)
        self.pet.show()
        if show_panel:
            self.panel.show()
        self.hello_timer = QTimer(self.pet)
        self.hello_timer.setSingleShot(True)
        self.hello_timer.timeout.connect(self.welcome)
        self.hello_timer.start(800)
        self.apply_services()

    def apply_services(self):
        self.weather.apply_settings()
        self.system_monitor.apply_settings()
        self.voice.apply_settings()
        self.google.apply_settings()
        self.reminders.check_due()
        self.flush_notices()
        if self.settings.get('voice_mode') != 'ptt':
            self.recognition.cancel()
        self.panel.mute_button.setVisible(self.settings.get('voice_mode') in ('spoken','ptt'))
        self.panel.mute_button.blockSignals(True)
        self.panel.mute_button.setChecked(not self.settings.get('voice_muted'))
        self.panel.mute_button.blockSignals(False)

    def review_transcription(self, text):
        previous = self.panel.input.text().strip()
        self.panel.input.setText((previous + ' ' + text).strip())
        self.panel.input.setFocus()

    def set_muted(self, muted):
        self.settings.update(voice_muted=muted)
        self.panel.preferences.features.controls['voice_muted'].setChecked(muted)
        self.voice.apply_settings()

    def speech_reaction(self, speaking):
        if (speaking and self.pet.activity == 'idle' and not self.pet.gesture and
                self.focus_deadline is None and self.pet.isVisible()):
            self.perform_gesture('tail_wag')

    def download_model(self, kind):
        directory = QFileDialog.getExistingDirectory(self.panel.preferences, 'Choose a model download folder')
        if not directory:
            return
        detail = ('Piper en_US-lessac-medium voice plus configuration/model card (roughly 60 MB). Review the voice license at huggingface.co/rhasspy/piper-voices.'
                  if kind == 'piper' else 'Multilingual Faster Whisper tiny (roughly 75 MB). Larger models can be installed manually for better Tagalog accuracy.')
        answer = QMessageBox.question(self.panel.preferences, 'Download optional local model?',
            detail + '\n\nDownloads from Hugging Face to the selected folder. Optional speech packages must be installed. Continue?')
        if answer == QMessageBox.Yes:
            self.voice.download(kind, directory)

    def model_downloaded(self, kind, path):
        key = 'piper_model' if kind == 'piper' else 'whisper_model'
        self.panel.preferences.features.controls[key].setText(path)

    def connect_google(self, kind):
        description = ('Read upcoming events from your primary calendar. No event creation or editing.'
                       if kind == 'calendar' else 'Read task lists and tasks. Creating/completing a cloud task requires another explicit confirmation each time.')
        answer = QMessageBox.question(self.tools, 'Authorize Google ' + kind.title() + '?',
            description + '\n\nYour browser will open Google’s desktop OAuth flow. Tokens must be stored in the operating system’s credential store. Continue?')
        if answer == QMessageBox.Yes:
            self.google.connect_account(kind, self.settings.get('google_client_file') or '')

    def google_connection_changed(self, kind, enabled):
        self.panel.preferences.features.controls['google_' + kind + '_enabled'].setChecked(enabled)

    def handle_message(self, text):
        try:
            local = self.reminders.handle_message(text)
        except (sqlite3.Error, ValueError, OSError):
            self.answer('Local productivity data is unavailable. Existing data was left unchanged.')
            return
        if local is not None:
            self.answer(local)
            return
        if re.search(r"(?:what(?:'s| is)|show|view).*(?:my schedule|my calendar|today.?s (?:schedule|meetings)|upcoming meetings)", text, re.I):
            if not self.settings.get('google_calendar_enabled'):
                self.answer('Connect read-only Google Calendar in Tools → Google to see your real schedule.')
            elif self.google.events and self.google.calendar_updated_at:
                self.answer(schedule_summary(self.google.events, self.settings.get('reminder_timezone') or '') +
                            '\nLast retrieved: ' + self.google.calendar_updated_at.astimezone().strftime('%Y-%m-%d %H:%M'))
            else:
                self._calendar_reply = True
                self.google.refresh_calendar()
            return
        self.companion.send(text)

    def google_status(self, kind, text):
        if kind=='calendar' and self._calendar_reply and self.google.jobs[kind].process is None:
            self._calendar_reply = False
            self.answer(text)

    def calendar_received(self, events):
        if self._calendar_reply:
            self._calendar_reply = False
            self.answer(schedule_summary(events, self.settings.get('reminder_timezone') or ''))

    def deliver_reminder(self, item):
        self.queue_notice({'kind':'reminder','id':item['id'],'title':'Reminder','message':item['title']})

    def deliver_calendar_event(self, item):
        self.queue_notice({'kind':'calendar','id':item['notice_key'],'title':'Upcoming event',
                           'message':item['display'] + ' · ' + item['title']})

    def queue_notice(self, item):
        if not any(entry['kind']==item['kind'] and entry['id']==item['id'] for entry in self._pending_notices):
            self._pending_notices.append(item)
        self.flush_notices()

    def flush_notices(self):
        if not self.settings.get('notifications') or (self.settings.get('reminder_quiet_focus') and self.focus_deadline is not None):
            return
        pending, self._pending_notices = self._pending_notices, []
        for item in pending:
            if item['kind']=='calendar' and not self.settings.get('google_calendar_enabled'):
                continue
            if item['kind']=='reminder' and self.reminders.store:
                if not any(row['id']==item['id'] for row in self.reminders.store.reminders()):
                    continue
                self.reminders.acknowledge(item['id'])
            elif item['kind']=='calendar' and self.reminders.store:
                self.reminders.store.mark_event_notified(item['id'])
            self.panel.add_message(item['title'], item['message'])
            if self.tray.isVisible(): self.tray.showMessage(item['title'], item['message'])
            else: self.pet.say(item['message'])
            if self.pet.activity=='idle' and not self.pet.gesture and self.pet.isVisible():
                self.perform_gesture('tail_wag')

    def choose_location(self, place):
        self.settings.update(weather_city=place['name'], weather_latitude=place['latitude'],
                             weather_longitude=place['longitude'], weather_enabled=True)
        self.panel.preferences.features.controls['weather_enabled'].setChecked(True)
        self.panel.preferences.features.weather_location.setText('Selected city: ' + place['name'])
        self.weather.apply_settings()

    def weather_reaction(self, data):
        if (self.settings.get('weather_reactions') and not data.get('cached') and self.focus_deadline is None
                and self.pet.activity == 'idle' and not self.pet.gesture and not self.pet.greeting_until
                and self.pet.animator.state not in ('leaving', 'dragged') and self.pet.isVisible()):
            self.perform_gesture(data['reaction'])
            self.pet.say(data['message'])

    def ambient_notice(self, message, reaction):
        if not self.settings.get('notifications') or self.focus_deadline is not None:
            return
        self.pet.say(message)
        if self.pet.activity == 'idle' and not self.pet.gesture and self.pet.isVisible():
            self.perform_gesture(reaction)
        if self.tray.isVisible():
            self.tray.showMessage('Biscuit', message)

    def welcome(self):
        if self.pet.activity in ("idle", "explore") and not self.pet.greeting_until:
            self.pet.say(f"Hi, I’m {self.settings.get('name')}! Drag me anywhere. Double-click to chat. 🐾")

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
        if self.pet.pet():
            self.panel.perform_gesture("happy")

    def perform_gesture(self, state):
        if not self.pet.isVisible():
            self.summon()
        if self.pet.perform_gesture(state):
            self.panel.perform_gesture(state)

    def toggle_sleep(self):
        self.activate_activity("nap")

    def sync_wander(self, enabled):
        self.settings.update(wander=enabled)
        self.wander.blockSignals(True)
        self.wander.setChecked(enabled)
        self.wander.blockSignals(False)

    def set_wander(self, enabled):
        if enabled:
            self.activate_activity("explore", toggle=False)
        elif self.pet.activity == "explore":
            self.activate_activity("idle")
        else:
            self.sync_wander(False)

    def sync_activity(self, key):
        self.panel.set_activity(key)
        for action, activity in ((self.work_action, "work"), (self.follow_action, "follow")):
            action.setChecked(self.pet.activity == activity)
        self.sleep_action.setText("Wake up" if self.pet.activity == "nap" else "Take a nap")

    def stop_focus(self):
        self.focus_deadline = None
        self.panel.set_focus_remaining(None)
        self.flush_notices()

    def activate_activity(self, key, toggle=True):
        if key not in ("idle", "explore", "work", "greet", "nap", "follow"):
            raise ValueError(f"Unknown companion activity: {key}")
        if not self.pet.isVisible():
            self.summon()
        if key == "greet":
            self.pet.greet()
            return
        if toggle and key != "idle" and self.pet.activity == key:
            key = "idle"
        self.stop_focus()
        self.sync_wander(key == "explore")
        self.pet.set_activity(key)
        if key == "work":
            self.focus_deadline = time.monotonic() + 25 * 60
            self.focus_tick()
        messages = {
            "explore": "Time for a tiny adventure. I’ll see what’s around!",
            "work": "Laptop ready! One small task, twenty-five cozy minutes. Let’s do this.",
            "nap": "Curling up for a little nap. Wake me whenever you need me…",
            "follow": "Lead the way with your mouse. I’ll follow at a comfy distance. Choose Rest here to stop.",
            "idle": "I’ll stay right here. Tiny paws, excellent company.",
        }
        self.pet.say(messages[key])

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
        self.voice.speak(message)
        if (self.pet.activity != "nap" and not self.pet.gesture
                and self.pet.animator.state not in ("sleeping", "leaving", "dragged")):
            self.pet.set_state("happy")

    def toggle_focus(self):
        self.activate_activity("work")

    def focus_tick(self):
        if self.focus_deadline is None:
            return
        remaining = max(0, math.ceil(self.focus_deadline - time.monotonic()))
        self.panel.set_focus_remaining(remaining)
        if remaining == 0:
            self.stop_focus()
            self.pet.set_activity("idle")
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
        self.weather.shutdown()
        self.system_monitor.shutdown()
        self.recognition.shutdown()
        self.reminders.shutdown()
        self.google.shutdown()
        self.voice.shutdown()
        self.tools.hide()
        self.panel.preferences.shutdown()
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
