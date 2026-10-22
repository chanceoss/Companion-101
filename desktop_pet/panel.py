"""Native companion sidebar + chat, with Preferences behind the small gear button."""

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QBoxLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .activities import ACTIVITIES, SCENES
from .animations import Animator
from .chat_widgets import ChatHistory, ConversationFrame
from .gestures import GESTURES
from .preferences import PreferencesDialog
from .providers import local_endpoint
from .rendering import draw_character
from .theme import garden, icon, load_fonts, paw, sparkle, ui_font

STYLE = """
QWidget {color: #674c3d; font-family: 'Nunito'; font-size: 15px;}
QWidget#panel, QDialog#preferences, QDialog#tools {background: #fcf8f2;}
QWidget#featurePage, QWidget#toolPage {background: #fcf8f2;}
QLabel#eyebrow {color: #967a69; font-size: 12px; font-weight: 800; letter-spacing: 2.5px;}
QLabel#title {font-family: 'Fredoka'; color: #482b22; font-size: 43px; font-weight: 600;}
QLabel#subtitle {color: #a38b7d; font-size: 19px;}
QLabel#petName {font-family: 'Fredoka'; color: #482b22; font-size: 32px; font-weight: 600;}
QLabel#petTagline {color: #957e6d; font-size: 15px;}
QLabel#pill {color: #60824a; background: #edf3e3; border-radius: 19px; padding: 6px 15px; font-size: 17px; font-weight: 700;}
QLabel#hint {color: #ab9585; font-size: 12px;}
QLabel#state {color: #8f9c70; font-size: 12px;}
QLabel#section {color: #a17f64; font-size: 11px; font-weight: 800; letter-spacing: 1.5px;}
QLabel#dialogTitle {font-family: 'Fredoka'; color: #593b2c; font-size: 28px; font-weight: 500;}
QFrame#chatPanel {background: #fffcf8; border: 1px solid #efe4d8; border-radius: 23px;}
QLabel#chatTitle {color: #a9612d; font-size: 20px; font-weight: 800;}
QFrame#composer {background: #fffdfa; border: 1px solid #ebdece; border-radius: 15px;}
QLineEdit {background: #fffdf9; border: 1px solid #e5d6c5; border-radius: 10px; min-height: 22px; padding: 11px; selection-background-color: #e8d3b1;}
QLineEdit:focus {border-color: #c98e55;}
QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit {background: #fffdf9; border: 1px solid #e5d6c5; border-radius: 8px; padding: 5px; min-height: 22px;}
QComboBox {padding-right: 22px;}
QComboBox::drop-down {border: 0; width: 20px;}
QComboBox QAbstractItemView {background: #fffaf2; selection-background-color: #efdfc5; color: #674c3d;}
QToolBox::tab {background: #f4eddf; color: #806345; border-radius: 8px; padding: 7px; font-weight: 700;}
QToolBox::tab:selected {background: #ecebd8; color: #61754c;}
QListWidget {background: #fffdf9; border: 1px solid #eadac6; border-radius: 10px; padding: 5px;}
QFrame#composer QLineEdit {background: transparent; border: 0; min-height: 20px; padding: 8px 4px; font-size: 15px;}
QPushButton {background: #fffaf2; border: 1px solid #eadac6; border-radius: 12px; padding: 9px 14px; font-weight: 700;}
QPushButton:hover {background: #f5ead8; border-color: #d6ae7d;}
QPushButton:pressed {background: #ecdbbf;}
QPushButton:disabled {background: #f2ebe1; color: #bca792; border-color: #e9ded0;}
QPushButton#primary {background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #c88b55,stop:1 #b87446); color: white; border: 1px solid #bd8050;}
QPushButton#primary:hover {background: #ae7042;}
QPushButton#primary:disabled {background: #d8b89b; color: #fff8ee; border-color: #d8b89b;}
QPushButton#quiet {background: transparent; color: #ac8a6b; border: 0; padding: 6px; font-size: 12px;}
QPushButton#focus {background: #f1f3e5; color: #7b855c; font-size: 13px;}
QToolButton {background: transparent; border: 0; border-radius: 10px; padding: 6px;}
QToolButton:hover {background: #f4eadc;}
QToolButton#gear {background: #fff8ee; border: 1px solid #ecd7be; border-radius: 14px;}
QToolButton#gear:hover {background: #f7e9d5; border-color: #dcb887;}
QCheckBox {spacing: 9px; padding: 4px 0;}
QCheckBox::indicator {width: 17px; height: 17px; border: 1px solid #d9c7af; border-radius: 5px; background: #fffdfa;}
QCheckBox::indicator:checked {background: #b6824e; border: 4px solid #efdfc5;}
QSlider::groove:horizontal {height: 5px; border-radius: 2px; background: #e7dccb;}
QSlider::sub-page:horizontal {background: #c28b52; border-radius: 2px;}
QSlider::handle:horizontal {width: 16px; margin: -6px 0; border-radius: 8px; background: #b87c43;}
QScrollArea {background: transparent; border: 0;}
QScrollBar:vertical {width: 6px; background: transparent;}
QScrollBar::handle:vertical {background: #dfd3c1; border-radius: 3px; min-height: 28px;}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height: 0;}
QToolTip {background: #fff9ee; color: #62462f; border: 1px solid #dfcbb0; padding: 5px;}
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


class BrandHeader(QWidget):
    compact = False

    def paintEvent(self, event):
        if self.compact:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paw(p, 405, 26, 20, "#f4d6b2", 16)
        paw(p, 391, 61, 18, "#f4d6b2", -20)


class ActivityButton(QAbstractButton):
    def __init__(self, activity, sprites, parent=None):
        super().__init__(parent)
        self.activity = activity
        self.compact = False
        self.sprite = sprites.frame(activity.scene, 0)
        self.setText(
            {"work": "Work", "greet": "Hi", "nap": "Nap", "follow": "Follow"}.get(
                activity.key, "Explore"
            )
        )
        self.setAccessibleName(activity.title)
        self.setToolTip(activity.description)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(92, 117)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(84, 90) if self.compact else QSize(128, 130)

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        selected = self.isChecked() or self.hasFocus()
        p.setBrush(QColor("#fff8e9" if selected else "#fffaf4"))
        p.setPen(
            QPen(QColor("#f3b15b" if selected else "#f2e9dd"), 1.8 if selected else 0.8)
        )
        p.drawRoundedRect(QRectF(1.5, 1.5, self.width() - 3, self.height() - 3), 24, 24)
        size = min(self.width() - 15, self.height() - 30)
        x = (self.width() - size) / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.activity.color))
        p.drawEllipse(QRectF(x + 2, 7, size - 4, size - 4))
        p.drawPixmap(QRectF(x, 3, size, size), self.sprite, QRectF(self.sprite.rect()))
        p.setPen(QColor("#a65e27" if selected else "#8d7463"))
        p.setFont(ui_font(13 if self.compact else 16, 700 if selected else 600))
        p.drawText(
            QRectF(2, self.height() - 29, self.width() - 4, 25),
            Qt.AlignCenter,
            self.text(),
        )


class GardenCard(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 25, 25)
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#f0f1dd"))
        gradient.setColorAt(0.55, QColor("#fcf6e9"))
        gradient.setColorAt(1, QColor("#f5f1dd"))
        p.fillPath(path, gradient)
        p.setClipPath(path)
        garden(p, QRectF(self.rect()))


class Portrait(QAbstractButton):
    def __init__(self, sprites):
        super().__init__()
        self.sprites = sprites
        self.setFixedHeight(205)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Give Biscuit a little love")
        self.setToolTip("Click to give a little love")
        self.setFocusPolicy(Qt.StrongFocus)
        self.activity = "idle"
        self.gesture = None
        self._paused_elapsed = 0
        self.animator = Animator(library=sprites.animation_library)
        self.pose = self.animator.advance(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)

    def showEvent(self, event):
        self.timer.start(50)

    def hideEvent(self, event):
        self.timer.stop()

    def animate(self):
        self.pose = self.animator.advance(0.05)
        if self.gesture and self.animator.state != self.gesture:
            self.gesture = None
            self.animator.set_state(SCENES[self.activity])
            if self.activity == "greet":
                self.animator.elapsed = self._paused_elapsed
            self.pose = self.animator.advance(0)
        self.update()

    def set_activity(self, activity):
        self.activity = activity
        self.gesture = None
        self.animator.set_state(SCENES[activity])
        self.update()

    def perform_gesture(self, state):
        if not self.gesture:
            self._paused_elapsed = self.animator.elapsed
        self.gesture = state
        self.animator.set_state(state, restart=True)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#fbf6df"))
        for x, y, w, h in ((-20, 60, 80, 80), (18, 36, 65, 75), (55, 66, 50, 60)):
            p.drawEllipse(QRectF(x, y, w, h))
        p.setBrush(QColor("#e4eacd"))
        p.drawEllipse(QRectF(-50, 153, self.width() + 65, 110))
        sparkle(p, 38, 54, 12)
        sparkle(p, self.width() - 52, 29, 9)
        paw(p, self.width() - 32, 59, 19, "#edcd98", 10)
        p.setBrush(QColor(133, 132, 83, 22))
        p.drawEllipse(QRectF(self.width() / 2 - 68, self.height() - 18, 136, 11))
        w = min(self.width() - 8, 225)
        p.save()
        p.translate(self.width() / 2, self.height() - 12)
        draw_character(p, self.sprites, self.animator, self.pose, w)
        p.restore()
        garden(p, QRectF(0, self.height() - 22, self.width(), 22), corner=True)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#d4b07b"), 1, Qt.DashLine))
            p.drawRoundedRect(QRectF(3, 3, self.width() - 6, self.height() - 6), 16, 16)


class ControlPanel(QWidget):
    summon_requested = Signal()
    pet_requested = Signal()
    sleep_requested = Signal()
    scale_changed = Signal(int)
    message_sent = Signal(str)
    clear_requested = Signal()
    preferences_saved = Signal()
    focus_requested = Signal()
    quit_requested = Signal()
    activity_requested = Signal(str)
    gesture_requested = Signal(str)
    tools_requested = Signal(str)
    microphone_requested = Signal()
    mute_requested = Signal(bool)

    def __init__(self, settings, sprites, companion):
        super().__init__()
        load_fonts()
        self.settings, self.sprites, self.companion = settings, sprites, companion
        self.allow_close = False
        self._busy = False
        self.setObjectName("panel")
        self.setWindowTitle("Biscuit · A little company")
        self.setMinimumSize(480, 540)
        self.compact = None
        self._updating_layout = False
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(
            min(1100, available.width() - 64), min(960, available.height() - 64)
        )
        self.setStyleSheet(STYLE)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(28, 20, 28, 12)
        self.outer.setSpacing(20)
        self.outer.addWidget(self.build_header())
        body = self.body = QHBoxLayout()
        body.setSpacing(18)
        self.sidebar = self.build_sidebar()
        self.sidebar.setFixedWidth(306)
        body.addWidget(self.sidebar)
        self.chat_panel = self.build_chat()
        body.addWidget(self.chat_panel, 1)
        self.outer.addLayout(body, 1)
        footer = self.footer = label(
            "Drag your companion to move · Double-click the pet to chat · Right-click for more",
            "hint",
        )
        footer.setAlignment(Qt.AlignCenter)
        self.outer.addWidget(footer)
        self.preferences = PreferencesDialog(settings, companion, self)
        self.preferences.scale_changed.connect(self.scale_changed.emit)
        self.preferences.saved.connect(self.on_preferences_saved)
        self.preferences.quit_requested.connect(self.quit_requested.emit)
        self.preferences_shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        self.preferences_shortcut.activated.connect(self.open_preferences)
        self.refresh_mode()
        self.apply_layout()

    def build_header(self):
        header = self.brand_header = BrandHeader()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.eyebrow = label("COMPANION / 101", "eyebrow")
        self.brand_title = label("A little company.", "title")
        self.subtitle = label("Small paws. A brighter workday.", "subtitle")
        titles.addWidget(self.eyebrow)
        titles.addWidget(self.brand_title)
        titles.addWidget(self.subtitle)
        row.addLayout(titles)
        row.addStretch()
        status = QHBoxLayout()
        status.setSpacing(12)
        self.mode = label("●  Offline", "pill")
        self.mode.setFixedHeight(38)
        status.addWidget(self.mode)
        self.settings_button = QToolButton()
        self.settings_button.setObjectName("gear")
        self.settings_button.setIcon(icon("gear", size=27))
        self.settings_button.setIconSize(QSize(27, 27))
        self.settings_button.setFixedSize(46, 46)
        self.settings_button.setAccessibleName("Open preferences")
        self.settings_button.setToolTip("Preferences (Ctrl+,)")
        self.settings_button.setFocusPolicy(Qt.StrongFocus)
        self.settings_button.setCursor(Qt.PointingHandCursor)
        self.settings_button.clicked.connect(self.open_preferences)
        status.addWidget(self.settings_button)
        row.addLayout(status)
        return header

    def build_sidebar(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setAccessibleName("Companion and activities")
        scroll.viewport().setAutoFillBackground(False)
        content = QWidget()
        content.setObjectName("sidebarContents")
        content.setStyleSheet("QWidget#sidebarContents {background: transparent;}")
        content.setAutoFillBackground(False)
        rows = self.sidebar_rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 0, 5, 0)
        rows.setSpacing(10)
        card = GardenCard()
        card_rows = self.card_rows = QVBoxLayout(card)
        card_rows.setContentsMargins(13, 7, 13, 18)
        card_rows.setSpacing(9)
        self.portrait = Portrait(self.sprites)
        self.portrait.clicked.connect(self.pet_requested.emit)
        card_rows.addWidget(self.portrait)
        self.name_strip = QWidget()
        names = QHBoxLayout(self.name_strip)
        names.setContentsMargins(0, 0, 0, 0)
        self.pet_name = label(self.settings.get("name"), "petName")
        self.pet_name.setMinimumWidth(0)
        names.addWidget(self.pet_name)
        stamp = QLabel()
        stamp.setPixmap(icon("paw", "#ebba86", 21).pixmap(21, 21))
        names.addWidget(stamp)
        names.addStretch()
        card_rows.addWidget(self.name_strip)
        self.tagline = label("Tiny buddy for your day.", "petTagline")
        card_rows.addWidget(self.tagline)
        grid = self.activity_grid = QGridLayout()
        grid.setSpacing(8)
        self.activity_buttons = {}
        for index, activity in enumerate(ACTIVITIES):
            tile = ActivityButton(activity, self.sprites)
            tile.clicked.connect(
                lambda checked=False, key=activity.key: self.activity_requested.emit(
                    key
                )
            )
            self.activity_buttons[activity.key] = tile
            if index == 4:
                tile.setFixedWidth(158)
                grid.addWidget(tile, 2, 0, 1, 2, Qt.AlignHCenter)
            else:
                grid.addWidget(tile, index // 2, index % 2)
        self.sleep_button = self.activity_buttons["nap"]
        card_rows.addLayout(grid)
        rows.addWidget(card)
        self.focus = button("◷  Focus together · 25 min", self.focus_requested.emit)
        self.focus.setObjectName("focus")
        self.focus.hide()
        rows.addWidget(self.focus)
        utility = QHBoxLayout()
        self.rest_button = button(
            "Rest here", lambda: self.activity_requested.emit("idle")
        )
        self.rest_button.setObjectName("quiet")
        utility.addWidget(self.rest_button)
        bring_back = button("Bring back ↗", self.summon_requested.emit)
        bring_back.setObjectName("quiet")
        utility.addWidget(bring_back)
        rows.addLayout(utility)
        self.state = label("●  Feeling cozy", "state")
        self.state.setAlignment(Qt.AlignCenter)
        rows.addWidget(self.state)
        rows.addStretch()
        scroll.setWidget(content)
        return scroll

    def build_chat(self):
        frame = QFrame()
        frame.setObjectName("chatPanel")
        rows = self.chat_rows = QVBoxLayout(frame)
        rows.setContentsMargins(16, 18, 16, 16)
        rows.setSpacing(12)
        heading = QHBoxLayout()
        chat_icon = QLabel()
        chat_icon.setPixmap(icon("chat", "#ba702f", 27).pixmap(27, 27))
        heading.addWidget(chat_icon)
        heading.addWidget(label("Chat", "chatTitle"))
        heading.addStretch()
        self.tools_button = QToolButton()
        self.tools_button.setText("Tools")
        self.tools_button.setAccessibleName("Companion tools")
        self.tools_button.setPopupMode(QToolButton.InstantPopup)
        self.tools_menu = QMenu(self.tools_button)
        self.tool_actions = {}
        for key, title in (("weather", "Weather"), ("system", "System status")):
            self.add_tool(key, title)
        self.tools_button.setMenu(self.tools_menu)
        heading.addWidget(self.tools_button)
        self.gesture_button = QToolButton()
        self.gesture_button.setText("Reactions")
        self.gesture_button.setIcon(icon("paw", "#b88042", 18))
        self.gesture_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.gesture_button.setAccessibleName("Biscuit reactions")
        self.gesture_button.setToolTip("A little stretch, a dance, or a playful reaction")
        self.gesture_button.setPopupMode(QToolButton.InstantPopup)
        self.gesture_menu = QMenu(self.gesture_button)
        self.gesture_actions = {}
        for state, title in GESTURES:
            action = self.gesture_menu.addAction(title)
            action.triggered.connect(
                lambda checked=False, key=state: self.gesture_requested.emit(key)
            )
            self.gesture_actions[state] = action
        self.gesture_button.setMenu(self.gesture_menu)
        heading.addWidget(self.gesture_button)
        self.mute_button = QToolButton()
        self.mute_button.setText("Sound")
        self.mute_button.setCheckable(True)
        self.mute_button.setChecked(not self.settings.get("voice_muted"))
        self.mute_button.setToolTip("Toggle spoken replies")
        self.mute_button.setAccessibleName("Mute or unmute Biscuit")
        self.mute_button.toggled.connect(
            lambda enabled: self.mute_requested.emit(not enabled)
        )
        self.mute_button.hide()
        heading.addWidget(self.mute_button)
        self.clear_button = QToolButton()
        self.clear_button.setIcon(icon("clear", "#bca28b", 19))
        self.clear_button.setAccessibleName("Clear conversation")
        self.clear_button.setToolTip("Clear conversation")
        self.clear_button.clicked.connect(self.clear_chat)
        heading.addWidget(self.clear_button)
        rows.addLayout(heading)
        divider = QFrame()
        divider.setFixedHeight(2)
        divider.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #c68c59,stop:.24 #c68c59,stop:.241 #f1e8de,stop:1 #f1e8de); border: 0;"
        )
        rows.addWidget(divider)
        self.chat_info = label("", "hint")
        self.chat_info.setWordWrap(True)
        rows.addWidget(self.chat_info)
        self.conversation_frame = ConversationFrame()
        history_rows = QVBoxLayout(self.conversation_frame)
        history_rows.setContentsMargins(2, 2, 2, 2)
        self.transcript = ChatHistory(self.sprites)
        history_rows.addWidget(self.transcript)
        rows.addWidget(self.conversation_frame, 1)
        self.add_message(self.settings.get("name"), "Hi! I’m here.")
        self.thinking = label("", "hint")
        self.thinking.hide()
        rows.addWidget(self.thinking)
        self.voice_status = label("", "hint")
        self.voice_status.setWordWrap(True)
        self.voice_status.setMinimumWidth(0)
        self.voice_status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.voice_status.hide()
        rows.addWidget(self.voice_status)
        self.fallback_button = button("Use offline reply", self.companion.retry_offline)
        self.fallback_button.setObjectName("quiet")
        self.fallback_button.hide()
        self.companion.fallback_available.connect(
            lambda text: self.offer_fallback(text)
        )
        self.companion.notice.connect(lambda text: self.add_message("Connection", text))
        self.companion.answered.connect(lambda text: self.fallback_button.hide())
        rows.addWidget(self.fallback_button)
        composer_row = QHBoxLayout()
        composer_row.setSpacing(10)
        composer = QFrame()
        composer.setObjectName("composer")
        composer.setMinimumHeight(52)
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(10, 3, 10, 3)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Say something to your companion…")
        self.input.setAccessibleName("Message to Biscuit")
        self.input.setMaxLength(4000)
        self.input.returnPressed.connect(self.send)
        composer_layout.addWidget(self.input, 1)
        self.microphone_button = QToolButton()
        self.microphone_button.setText("Mic")
        self.microphone_button.setAccessibleName("Start or stop voice recording")
        self.microphone_button.setToolTip(
            "Click to record; click again to stop. Review text before sending."
        )
        self.microphone_button.clicked.connect(self.microphone_requested.emit)
        composer_layout.addWidget(self.microphone_button)
        composer_row.addWidget(composer, 1)
        self.send_button = button("Send ↗", self.send, True)
        self.send_button.setFixedSize(92, 52)
        composer_row.addWidget(self.send_button)
        rows.addLayout(composer_row)
        return frame

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "chat_info"):
            self.apply_layout()

    def apply_layout(self):
        if self._updating_layout:
            return
        self._updating_layout = True
        try:
            compact = self.width() < 800
            changed = compact != self.compact
            self.compact = compact
            self.brand_header.compact = compact
            self.brand_header.update()
            self.eyebrow.setVisible(not compact)
            self.subtitle.setVisible(not compact)
            self.footer.setVisible(not compact)
            self.brand_title.setStyleSheet("font-size: 28px;" if compact else "")
            self.mode.setStyleSheet(
                "font-size: 13px; padding: 4px 10px; border-radius: 16px;"
                if compact
                else ""
            )
            self.mode.setFixedHeight(32 if compact else 38)
            self.settings_button.setFixedSize(
                36 if compact else 46, 36 if compact else 46
            )
            self.settings_button.setIconSize(
                QSize(23, 23) if compact else QSize(27, 27)
            )
            self.outer.setContentsMargins(
                *((16, 12, 16, 12) if compact else (28, 20, 28, 12))
            )
            self.outer.setSpacing(10 if compact else 20)
            self.body.setDirection(
                QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight
            )
            self.body.setSpacing(10 if compact else 18)
            self.portrait.setVisible(not compact)
            self.tagline.setVisible(not compact)
            self.state.setVisible(not compact)
            self.pet_name.setStyleSheet("font-size: 20px;" if compact else "")
            self.card_rows.setContentsMargins(
                *((8, 4, 8, 6) if compact else (13, 7, 13, 18))
            )
            self.card_rows.setSpacing(3 if compact else 9)
            self.sidebar_rows.setSpacing(3 if compact else 10)
            if changed:
                for tile in self.activity_buttons.values():
                    self.activity_grid.removeWidget(tile)
                self.activity_grid.setSpacing(4 if compact else 8)
                for index, tile in enumerate(self.activity_buttons.values()):
                    tile.compact = compact
                    tile.setMinimumSize(QSize(58, 86) if compact else QSize(92, 117))
                    tile.setMaximumWidth(16777215)
                    if compact:
                        self.activity_grid.addWidget(tile, 0, index)
                    elif index == 4:
                        tile.setFixedWidth(158)
                        self.activity_grid.addWidget(tile, 2, 0, 1, 2, Qt.AlignHCenter)
                    else:
                        self.activity_grid.addWidget(tile, index // 2, index % 2)
                    tile.updateGeometry()
                    tile.update()
            self.chat_rows.setContentsMargins(
                *((10, 10, 10, 10) if compact else (16, 18, 16, 16))
            )
            self.chat_rows.setSpacing(6 if compact else 12)
            self.chat_info.setVisible(not compact)
            self.thinking.setVisible(getattr(self, "_busy", False) and not compact)
            self.set_voice_status(getattr(self, "_voice_text", ""))
            if compact:
                self.sidebar.setMinimumWidth(0)
                self.sidebar.setMaximumWidth(16777215)
                self.sidebar.setFixedHeight(
                    162 + (40 if not self.focus.isHidden() else 0)
                )
            else:
                self.sidebar.setMinimumHeight(0)
                self.sidebar.setMaximumHeight(16777215)
                self.sidebar.setFixedWidth(
                    max(248, min(326, round((self.width() - 74) * 0.33)))
                )
        finally:
            self._updating_layout = False

    def open_preferences(self):
        self.preferences.showNormal()
        self.preferences.raise_()
        self.preferences.activateWindow()

    def set_sprites(self, sprites):
        self.sprites = sprites
        self.portrait.sprites = sprites
        self.portrait.animator.set_library(sprites.animation_library)
        self.portrait.pose = self.portrait.animator.advance(0)
        self.portrait.update()
        for tile in self.activity_buttons.values():
            tile.sprite = sprites.frame(tile.activity.scene, 0)
            tile.update()
        self.transcript.set_sprites(sprites)
        for state, title in GESTURES:
            self.gesture_actions[state].setText(sprites.spec(state).get("menu_label", title))
        self.set_state(self.portrait.animator.state)

    def refresh_identity(self):
        name = self.settings.get("name")
        self.pet_name.setText(name)
        self.setWindowTitle(f"{name} · A little company")
        self.preferences.setWindowTitle(f"{name} · Preferences")
        self.preferences.quit_button.setText(f"Quit {name}")
        self.preferences.provider.setItemText(
            self.preferences.provider.findData("offline"), f"Offline — {name} responses"
        )
        self.portrait.setAccessibleName(f"Give {name} a little love")
        self.gesture_button.setAccessibleName(f"{name} reactions")
        self.mute_button.setAccessibleName(f"Mute or unmute {name}")
        self.input.setAccessibleName(f"Message to {name}")
        if self._busy:
            self.input.setPlaceholderText(f"{name} is thinking…")

    def on_preferences_saved(self):
        self.refresh_identity()
        self.refresh_mode()
        self.preferences_saved.emit()

    def refresh_mode(self):
        ai = self.settings.get("provider")
        local = ai and local_endpoint(self.settings.get("endpoint"))
        self.mode.setText(
            "●  Local AI" if local else "●  AI enabled" if ai else "●  Offline"
        )
        self.mode.setToolTip(
            "AI messages go to your configured local server"
            if local
            else "Chat uses your configured remote AI provider"
            if ai
            else "Offline companion replies stay on this device"
        )
        self.chat_info.setVisible(not self.compact)
        self.chat_info.setText(
            "Local AI · Messages go to your local server."
            if local
            else "Cloud AI · Messages go to your chosen provider."
            if ai
            else "A cozy place to pause. Offline replies stay on this device."
        )

    def set_state(self, state):
        titles = {
            "sleeping": "Dreaming",
            "walking": "On a stroll",
            "happy": "Feeling loved",
            "dragged": "Wheee!",
            "idle": "Feeling cozy",
            "entering": "Hello there",
            "leaving": "See you soon",
            "working": "Working together",
            "greeting": "Hello, friend!",
            "exploring": "Looking around",
            "following": "Right behind you",
        }
        title = self.sprites.spec(state).get(
            "label", titles.get(state, state.replace("_", " ").capitalize())
        )
        self.state.setText("●  " + title)

    def set_activity(self, key):
        for activity, tile in self.activity_buttons.items():
            tile.setChecked(activity == key)
        self.portrait.set_activity(key)
        self.sleep_button.setText("Wake" if key == "nap" else "Nap")
        self.sleep_button.setAccessibleName("Wake up" if key == "nap" else "Take a nap")

    def perform_gesture(self, state):
        self.portrait.perform_gesture(state)

    def set_focus_remaining(self, seconds):
        self.focus.setVisible(seconds is not None)
        if seconds is not None:
            self.focus.setText(f"◷  {seconds // 60:02d}:{seconds % 60:02d} · Stop")
            self.activity_buttons["work"].setText(
                f"{seconds // 60:02d}:{seconds % 60:02d}"
            )
        else:
            self.focus.setText("◷  Focus together · 25 min")
            self.activity_buttons["work"].setText("Work")
        self.apply_layout()

    def add_message(self, who, message, mine=False, error=False):
        self.transcript.add_message(who, message, mine, error)

    def send(self):
        message = self.input.text().strip()
        if message and self.send_button.isEnabled():
            self.fallback_button.hide()
            self.input.clear()
            self.add_message("You", message, True)
            self.message_sent.emit(message)

    def offer_fallback(self, text):
        self.add_message("Connection", text)
        self.fallback_button.show()

    def add_tool(self, key, title):
        action = self.tools_menu.addAction(title)
        action.triggered.connect(lambda checked=False: self.tools_requested.emit(key))
        self.tool_actions[key] = action

    def set_voice_status(self, text):
        self._voice_text = text
        self.voice_status.setWordWrap(not self.compact)
        self.voice_status.setMaximumHeight(22 if self.compact else 16777215)
        self.voice_status.setToolTip(text)
        self.voice_status.setText(
            self.voice_status.fontMetrics().elidedText(
                text, Qt.ElideRight, max(160, self.chat_panel.width() - 32)
            )
            if self.compact
            else text
        )
        self.voice_status.setVisible(bool(text))

    def set_listening(self, listening):
        self.microphone_button.setText("Stop" if listening else "Mic")

    def set_busy(self, busy):
        self._busy = busy
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.thinking.setText("A tiny thought is on its way…" if busy else "")
        self.thinking.setVisible(busy and not self.compact)
        self.input.setPlaceholderText(
            f"{self.settings.get('name')} is thinking…" if busy else "Say something to your companion…"
        )
        if not busy and self.isActiveWindow() and not self.preferences.isVisible():
            self.input.setFocus()

    def clear_chat(self):
        self.clear_requested.emit()
        self.transcript.clear()
        self.add_message(self.settings.get("name"), "A fresh little start. I’m here.")

    def open(self, chat=False):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if chat:
            self.input.setFocus()
            QTimer.singleShot(0, self.input.setFocus)

    def closeEvent(self, event):
        self.preferences.hide()
        if self.allow_close:
            event.accept()
            return
        event.ignore()
        self.hide()
