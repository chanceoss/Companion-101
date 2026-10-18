"""The former Preferences tab, now opened by the compact gear button."""
import sys
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSlider,
                               QVBoxLayout, QWidget, QLayout)
from .storage import startup_enabled, set_startup
from .ai import validate_endpoint


class PreferencesDialog(QDialog):
    scale_changed = Signal(int)
    saved = Signal()
    quit_requested = Signal()

    def __init__(self, settings, companion, parent=None):
        super().__init__(parent)
        self.settings, self.companion = settings, companion
        self.setWindowTitle("Biscuit · Preferences")
        self.setObjectName("preferences")
        self.setMinimumSize(460, 500)
        self.resize(560, 740)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 18)
        heading = QLabel("Make yourself at home.")
        heading.setObjectName("dialogTitle")
        outer.addWidget(heading)
        subtitle = QLabel("A few little things, just the way you like them.")
        subtitle.setObjectName("hint")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.viewport().setAutoFillBackground(False)
        page = QWidget()
        page.setObjectName("preferencesContents")
        page.setStyleSheet("QWidget#preferencesContents {background: transparent;}")
        page.setAutoFillBackground(False)
        layout = QVBoxLayout(page)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        layout.setContentsMargins(0, 16, 8, 12)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setSpacing(12)
        self.name = QLineEdit(settings.get("name"))
        self.name.setMaxLength(30)
        form.addRow("Pet’s name", self.name)
        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(60, 150)
        self.scale.setValue(settings.get("scale"))
        self.size_label = QLabel(f"{self.scale.value()}%")
        self.scale.valueChanged.connect(lambda n: self.size_label.setText(f"{n}%"))
        self.scale.valueChanged.connect(self.scale_changed.emit)
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.scale, 1)
        scale_row.addWidget(self.size_label)
        form.addRow("Pet size", scale_row)
        layout.addLayout(form)
        size_note = QLabel("Pet size updates immediately. Save companion preferences here; save the AI connection separately below.")
        size_note.setObjectName("hint")
        size_note.setWordWrap(True)
        layout.addWidget(size_note)
        self.reminders = QCheckBox("Gentle stretch reminders every 25 minutes")
        self.reminders.setChecked(settings.get("reminders"))
        layout.addWidget(self.reminders)
        self.startup = QCheckBox("Meet me when Windows starts")
        self.startup.setChecked(startup_enabled())
        self.startup.setEnabled(sys.platform == "win32")
        layout.addWidget(self.startup)
        layout.addSpacing(8)
        section = QLabel("OPTIONAL AI CONNECTION")
        section.setObjectName("section")
        layout.addWidget(section)
        note = QLabel("Offline mode is always available. With AI enabled, messages and recent conversation are sent to your chosen provider. No screen capture, files, or desktop control.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.provider = QCheckBox("Use an OpenAI-compatible AI provider")
        self.provider.setChecked(settings.get("provider"))
        layout.addWidget(self.provider)
        ai_form = QFormLayout()
        ai_form.setSpacing(12)
        self.endpoint = QLineEdit(settings.get("endpoint"))
        self.model = QLineEdit(settings.get("model"))
        self.key = QLineEdit(companion.key)
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("API key (optional for a local provider)")
        ai_form.addRow("API base URL", self.endpoint)
        ai_form.addRow("Model", self.model)
        ai_form.addRow("API key", self.key)
        layout.addLayout(ai_form)
        self.remember = QCheckBox("Remember key in the operating system’s credential store")
        self.remember.setChecked(companion.remember_key)
        self._saved_key = companion.key
        self._saved_remember = companion.remember_key
        layout.addWidget(self.remember)
        key_note = QLabel("Keys never go in the preferences file. Uncheck and save to remove a saved key. Provider fees may apply.")
        key_note.setObjectName("hint")
        key_note.setWordWrap(True)
        layout.addWidget(key_note)
        self.ai_save_button = QPushButton("Save AI connection")
        self.ai_save_button.setAutoDefault(False)
        self.ai_save_button.clicked.connect(self.save_ai)
        layout.addWidget(self.ai_save_button)
        self.ai_status = QLabel("Completed conversation stays until you use Clear conversation.")
        self.ai_status.setObjectName("hint")
        self.ai_status.setWordWrap(True)
        layout.addWidget(self.ai_status)
        self.ai_fields = (self.endpoint, self.model, self.key)
        for field in self.ai_fields:
            field.installEventFilter(self)
        self.save_button = QPushButton("Save preferences")
        self.save_button.setObjectName("primary")
        self.save_button.setDefault(True)
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self.save)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        layout.addStretch()
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        outer.addWidget(self.status)
        footer = QHBoxLayout()
        quit_button = QPushButton("Quit Biscuit")
        quit_button.setObjectName("quiet")
        quit_button.setAutoDefault(False)
        quit_button.clicked.connect(self.quit_requested.emit)
        footer.addWidget(quit_button)
        footer.addStretch()
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        footer.addWidget(self.close_button)
        footer.addWidget(self.save_button)
        outer.addLayout(footer)

    def save(self):
        try:
            if sys.platform == "win32" and self.startup.isChecked() != startup_enabled():
                set_startup(self.startup.isChecked())
            self.settings.update(name=self.name.text().strip() or "Biscuit", reminders=self.reminders.isChecked(),
                                 scale=self.scale.value())
            self.status.setText("Preferences saved. Make yourself comfortable.")
        except (OSError, RuntimeError, ValueError) as exc:
            self.status.setText(str(exc))
        self.saved.emit()

    def save_ai(self):
        enabled = self.provider.isChecked()
        endpoint, model = self.endpoint.text().strip().rstrip("/"), self.model.text().strip()
        key, remember = self.key.text().strip(), self.remember.isChecked()
        try:
            if enabled:
                if not endpoint or not model:
                    raise ValueError("Enter an API base URL and model to enable AI.")
            if endpoint:
                validate_endpoint(endpoint)
            changed = (enabled != self.settings.get("provider") or endpoint != self.settings.get("endpoint")
                       or model != self.settings.get("model") or key != self._saved_key)
            self.settings.update(provider=enabled, endpoint=endpoint, model=model)
            if changed:
                self.companion.cancel_pending()
            if key != self._saved_key or remember != self._saved_remember:
                self.companion.save_key(key, remember)
            self._saved_key, self._saved_remember = key, remember
            self.ai_status.setText("AI connection saved. Your completed conversation is unchanged.")
        except (OSError, RuntimeError, ValueError) as exc:
            self.ai_status.setText(str(exc))
        self.saved.emit()

    def eventFilter(self, source, event):
        if source in self.ai_fields and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.save_ai()
            return True
        return super().eventFilter(source, event)
