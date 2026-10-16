import html
import math
import sys
from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QLinearGradient
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QTabWidget, QFrame, QTextBrowser, QLineEdit, QCheckBox, QSlider, QFormLayout,
    QMessageBox, QScrollArea)
from .storage import startup_enabled, set_startup

STYLE = """
QWidget { color: #46382f; font-family: 'Segoe UI'; font-size: 13px; }
QWidget#panel { background: #faf8f3; }
QLabel#eyebrow { color: #8d806f; font-size: 10px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 25px; font-weight: 700; color: #3c3028; }
QLabel#subtitle { color: #938778; font-size: 12px; }
QLabel#pill { color: #5f7951; background: #eaf0e2; border-radius: 11px; padding: 5px 10px; font-size: 11px; }
QLabel#section { color: #95846f; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
QLabel#cardTitle { font-size: 15px; font-weight: 600; }
QLabel#hint { color: #968b7e; font-size: 11px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: transparent; color: #9c8e7f; padding: 13px 18px; border-bottom: 2px solid #e9e3d9; font-weight: 600; }
QTabBar::tab:selected { color: #9d6038; border-bottom: 2px solid #bd8555; font-weight: 600; }
QFrame#card { border: 1px solid #e9e2d8; border-radius: 14px; background: #fffefa; }
QPushButton { background: #f2ece2; border: 1px solid #e7dccb; border-radius: 10px; padding: 10px 15px; font-weight: 600; }
QPushButton:hover { background: #e9dfcf; }
QPushButton:pressed { background: #decdb5; }
QPushButton:disabled { color: #b9ada0; background: #f2eee8; }
QPushButton#primary { background: #ae7446; color: white; border: 1px solid #ae7446; }
QPushButton#primary:hover { background: #98623a; }
QPushButton#quiet { background: transparent; border: 0; color: #a78360; padding: 6px; }
QLineEdit, QTextBrowser { background: #fffefa; border: 1px solid #e5dccf; border-radius: 9px; padding: 10px; selection-background-color: #d8b080; }
QLineEdit:focus { border-color: #b98757; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #d9cab5; border-radius: 5px; background: #fffefa; }
QCheckBox::indicator:checked { background: #ae7446; border: 4px solid #e8d7bf; }
QSlider::groove:horizontal { height: 5px; border-radius: 2px; background: #e7ddcd; }
QSlider::sub-page:horizontal { background: #b98451; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; border-radius: 8px; background: #ae7446; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: #faf8f3; }
QScrollBar:vertical { width: 7px; background: transparent; }
QScrollBar::handle:vertical { background: #dfd3c2; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #fff9ee; color: #46382f; border: 1px solid #dfd3c2; }
"""


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


class Portrait(QWidget):
    def __init__(self, sprites):
        super().__init__()
        self.sprites = sprites
        self.setFixedHeight(230)
        self.t = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)

    def showEvent(self, event):
        self.timer.start(50)

    def hideEvent(self, event):
        self.timer.stop()

    def animate(self):
        self.t += .05
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#f2efdf"))
        gradient.setColorAt(1, QColor("#e5ebd8"))
        p.setBrush(gradient)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 18, 18)
        p.setPen(QColor("#b7bd9e"))
        p.setFont(QFont("Segoe UI", 16))
        p.drawText(48, 70, "✧")
        p.drawText(self.width() - 70, 155, "✦")
        p.setFont(QFont("Segoe UI", 11))
        p.drawText(self.width() - 100, 52, "✧")
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(131, 117, 77, 20))
        p.drawEllipse(QRectF(self.width() / 2 - 79, self.height() - 27, 158, 12))
        pixmap = self.sprites.frame("idle", 0)
        w = 224
        h = w * pixmap.height() / pixmap.width()
        p.drawPixmap(QRectF((self.width() - w) / 2, self.height() - h - 19 + math.sin(self.t * 2) * 2, w, h), pixmap, QRectF(pixmap.rect()))
        p.setPen(QColor("#85906e"))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(15, self.height() - 16, "YOUR LITTLE DESKTOP COMPANION")


class ControlPanel(QWidget):
    summon_requested = Signal()
    pet_requested = Signal()
    sleep_requested = Signal()
    wander_changed = Signal(bool)
    scale_changed = Signal(int)
    message_sent = Signal(str)
    clear_requested = Signal()
    preferences_saved = Signal()
    focus_requested = Signal()
    quit_requested = Signal()

    def __init__(self, settings, sprites, companion):
        super().__init__()
        self.settings = settings
        self.allow_close = False
        self.companion = companion
        self.setObjectName("panel")
        self.setWindowTitle("Biscuit · A little company")
        self.setMinimumSize(480, 650)
        self.resize(540, 820)
        self.setStyleSheet(STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(27, 24, 27, 18)
        outer.setSpacing(6)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("COMPANION / 101", "eyebrow"))
        titles.addSpacing(4)
        titles.addWidget(label("A little company.", "title"))
        titles.addWidget(label("Small paws. A brighter workday.", "subtitle"))
        head.addLayout(titles)
        head.addStretch()
        self.mode = label("●  Offline", "pill")
        head.addWidget(self.mode, alignment=Qt.AlignTop)
        outer.addLayout(head)
        outer.addSpacing(13)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.home_tab(sprites), "Companion")
        self.tabs.addTab(self.chat_tab(), "Chat")
        self.tabs.addTab(self.settings_tab(), "Preferences")
        outer.addWidget(self.tabs, 1)
        footer = QHBoxLayout()
        footer.addWidget(label("Made for your desktop, and your day.", "hint"))
        footer.addStretch()
        quit_button = button("Quit", self.quit_requested.emit)
        quit_button.setObjectName("quiet")
        footer.addWidget(quit_button)
        outer.addLayout(footer)
        self.refresh_mode()

    def home_tab(self, sprites):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 8)
        layout.setSpacing(15)
        layout.addWidget(Portrait(sprites))
        name_row = QHBoxLayout()
        names = QVBoxLayout()
        self.pet_name = label(self.settings.get("name"), "title")
        names.addWidget(self.pet_name)
        names.addWidget(label("Your pocket-sized partner in everyday life.", "subtitle"))
        name_row.addLayout(names)
        name_row.addStretch()
        self.state = label("●  Feeling cozy", "pill")
        name_row.addWidget(self.state, alignment=Qt.AlignVCenter)
        layout.addLayout(name_row)
        actions = QHBoxLayout()
        actions.addWidget(button("♡  Give a little love", self.pet_requested.emit, True), 1)
        actions.addWidget(button("↗  Bring me back", self.summon_requested.emit), 1)
        layout.addLayout(actions)
        layout.addWidget(label("LITTLE RITUALS", "section"))
        card = QFrame()
        card.setObjectName("card")
        rows = QVBoxLayout(card)
        rows.setContentsMargins(15, 12, 15, 12)
        self.wander = QCheckBox("Explore my desktop")
        self.wander.setChecked(self.settings.get("wander"))
        self.wander.toggled.connect(self.wander_changed.emit)
        rows.addWidget(self.wander)
        rows.addWidget(label("Gentle wandering, with respect for your screen edges.", "hint"))
        row = QHBoxLayout()
        self.focus = button("◷  Focus together · 25 min", self.focus_requested.emit)
        row.addWidget(self.focus, 1)
        self.sleep_button = button("☾  Take a nap", self.sleep_requested.emit)
        row.addWidget(self.sleep_button)
        rows.addLayout(row)
        layout.addWidget(card)
        hint = label("Drag to move  ·  Click to pet  ·  Double-click to chat\nRight-click for more  ·  Find me in your system tray", "hint")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def chat_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 8)
        layout.setSpacing(12)
        self.chat_info = label("A cozy place to pause. Offline replies stay on this device.", "hint")
        self.chat_info.setWordWrap(True)
        layout.addWidget(self.chat_info)
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setOpenLinks(False)
        self.transcript.setStyleSheet("QTextBrowser { padding: 12px; }")
        layout.addWidget(self.transcript, 1)
        self.add_message(self.settings.get("name"), "Hey, friend. I’m happy you’re here. What’s on your mind?", False)
        self.thinking = label("", "hint")
        layout.addWidget(self.thinking)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Say something to your companion…")
        self.input.setMaxLength(4000)
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input, 1)
        self.send_button = button("Send ↗", self.send, True)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        clear = button("Clear conversation", self.clear_chat)
        clear.setObjectName("quiet")
        layout.addWidget(clear, alignment=Qt.AlignLeft)
        return page

    def settings_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 8, 8)
        layout.setSpacing(12)
        layout.addWidget(label("MAKE YOURSELF AT HOME", "section"))
        form = QFormLayout()
        form.setSpacing(10)
        self.name = QLineEdit(self.settings.get("name"))
        self.name.setMaxLength(30)
        form.addRow("Pet’s name", self.name)
        self.size_label = label(f"{self.settings.get('scale')}%")
        slider_row = QHBoxLayout()
        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(60, 150)
        self.scale.setValue(self.settings.get("scale"))
        self.scale.valueChanged.connect(lambda n: self.size_label.setText(f"{n}%"))
        self.scale.valueChanged.connect(self.scale_changed.emit)
        slider_row.addWidget(self.scale)
        slider_row.addWidget(self.size_label)
        form.addRow("Pet size", slider_row)
        layout.addLayout(form)
        self.reminders = QCheckBox("Gentle stretch reminders every 25 minutes")
        self.reminders.setChecked(self.settings.get("reminders"))
        layout.addWidget(self.reminders)
        self.startup = QCheckBox("Meet me when Windows starts")
        self.startup.setChecked(startup_enabled())
        self.startup.setEnabled(sys.platform == "win32")
        layout.addWidget(self.startup)
        layout.addSpacing(10)
        layout.addWidget(label("OPTIONAL AI CONNECTION", "section"))
        note = label("Offline mode is always available. With AI enabled, your messages and recent conversation are sent to the provider you choose. No screen capture, files, or desktop control.", "hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.provider = QCheckBox("Use an OpenAI-compatible AI provider")
        self.provider.setChecked(self.settings.get("provider"))
        layout.addWidget(self.provider)
        ai_form = QFormLayout()
        ai_form.setSpacing(10)
        self.endpoint = QLineEdit(self.settings.get("endpoint"))
        self.endpoint.setPlaceholderText("https://api.openai.com/v1")
        self.model = QLineEdit(self.settings.get("model"))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("API key (optional for local providers)")
        self.key.setText(self.companion.key)
        ai_form.addRow("API base URL", self.endpoint)
        ai_form.addRow("Model", self.model)
        ai_form.addRow("API key", self.key)
        layout.addLayout(ai_form)
        self.remember = QCheckBox("Remember key in the operating system’s credential store")
        self.remember.setChecked(bool(self.companion.key))
        layout.addWidget(self.remember)
        key_note = label("Keys are never written to the preferences file. Uncheck to remove a saved key. Provider fees may apply.", "hint")
        key_note.setWordWrap(True)
        layout.addWidget(key_note)
        layout.addWidget(button("Save preferences", self.save, True))
        self.saved = label("", "hint")
        self.saved.setWordWrap(True)
        layout.addWidget(self.saved)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def refresh_mode(self):
        ai = self.settings.get("provider")
        self.mode.setText("●  AI enabled" if ai else "●  Offline")
        self.chat_info.setText("AI enabled · Messages are sent to your configured provider." if ai else "Offline companion · Cozy preset replies, entirely on your device.")

    def set_state(self, state):
        titles = {"sleeping": "Dreaming", "walking": "Exploring", "happy": "Feeling loved", "dragged": "Wheee!", "idle": "Feeling cozy", "entering": "Hello there", "leaving": "See you soon"}
        self.state.setText("●  " + titles.get(state, state.title()))
        self.sleep_button.setText("☀  Wake up" if state == "sleeping" else "☾  Take a nap")

    def add_message(self, who, message, mine=False, error=False):
        color = "#a76248" if mine else "#6c815b"
        if error:
            color = "#b05245"
        escaped = html.escape(message).replace("\n", "<br>")
        self.transcript.append(f'<p style="margin-top:16px; color:{color}; font-size:11px;"><b>{html.escape(who)}</b></p><p style="color:#514335; line-height:150%; margin-bottom:14px;">{escaped}</p>')
        self.transcript.verticalScrollBar().setValue(self.transcript.verticalScrollBar().maximum())

    def send(self):
        message = self.input.text().strip()
        if message and self.send_button.isEnabled():
            self.input.clear()
            self.add_message("You", message, True)
            self.message_sent.emit(message)

    def set_busy(self, busy):
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.thinking.setText("A tiny thought is on its way…" if busy else "")

    def clear_chat(self):
        self.clear_requested.emit()
        self.transcript.clear()
        self.add_message(self.settings.get("name"), "A fresh little start. I’m here.")

    def save(self):
        try:
            if not self.model.text().strip() or not self.endpoint.text().strip():
                raise ValueError("Please enter an API base URL and model, even if you keep AI disabled for now.")
            if sys.platform == "win32" and self.startup.isChecked() != startup_enabled():
                set_startup(self.startup.isChecked())
            self.settings.update(name=self.name.text().strip() or "Biscuit", reminders=self.reminders.isChecked(),
                                 provider=self.provider.isChecked(), endpoint=self.endpoint.text().strip(),
                                 model=self.model.text().strip(), scale=self.scale.value())
            self.companion.clear()
            self.companion.save_key(self.key.text(), self.remember.isChecked())
            self.saved.setText("Preferences saved. Make yourself comfortable.")
        except (OSError, RuntimeError, ValueError) as exc:
            self.saved.setText(str(exc))
        self.pet_name.setText(self.settings.get("name"))
        self.refresh_mode()
        self.preferences_saved.emit()

    def open(self, chat=False):
        if chat:
            self.tabs.setCurrentIndex(1)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if chat:
            self.input.setFocus()

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
