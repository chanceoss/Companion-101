"""The former Preferences tab, now opened by the compact gear button."""

import sys
from copy import deepcopy
from urllib.parse import urlparse

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .ai_protocol import validate_connection, validate_endpoint, validate_key
from .avatars import AVATARS, avatar_spec
from .feature_preferences import FeatureSettings
from .providers import PRESETS, ProviderDiscovery, credential_account, provider_id
from .secrets import get_secret
from .storage import set_startup, startup_enabled


class ProviderSelector(QComboBox):
    """The former enable checkbox API remains compatible with existing callers."""

    def isChecked(self):
        return self.currentData() != "offline"

    def setChecked(self, checked):
        self.setCurrentIndex(self.findData("custom" if checked else "offline"))


class PreferencesDialog(QDialog):
    scale_changed = Signal(int)
    saved = Signal()
    quit_requested = Signal()
    general_applied = Signal()

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
        self.section_nav = QComboBox()
        self.section_nav.addItems(
            [
                "General",
                "AI connection",
                "Weather",
                "System",
                "Voice",
                "Reminders and Google",
                "Mini games",
            ]
        )
        self.section_nav.setAccessibleName("Preferences section")
        outer.addWidget(self.section_nav)
        scroll = self.scroll = QScrollArea()
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
        self.avatar = QComboBox()
        self.avatar.setAccessibleName("Companion avatar")
        for key, spec in AVATARS.items():
            self.avatar.addItem(spec.title, key)
        self.avatar.setCurrentIndex(max(0, self.avatar.findData(settings.get("avatar"))))
        self._draft_avatar = self.avatar.currentData()
        self.avatar.currentIndexChanged.connect(self.avatar_changed)
        self.avatar.setToolTip("Choose a companion, then Save preferences to apply. Your chat and activities are kept.")
        form.addRow("Companion", self.avatar)
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
        size_note = QLabel(
            "Pet size updates immediately. Save companion preferences here; save the AI connection separately below."
        )
        size_note.setObjectName("hint")
        size_note.setWordWrap(True)
        layout.addWidget(size_note)
        self.reminders = QCheckBox("Gentle stretch reminders every 25 minutes")
        self.reminders.setChecked(settings.get("reminders"))
        layout.addWidget(self.reminders)
        self.chat_reactions = QCheckBox("React during conversations")
        self.chat_reactions.setChecked(settings.get("chat_reactions"))
        self.chat_reactions.setToolTip(
            "Local expressions while thinking and replying. Focus sessions, naps, and your chosen reactions take priority."
        )
        layout.addWidget(self.chat_reactions)
        self.startup = QCheckBox("Meet me when Windows starts")
        self.startup.setChecked(startup_enabled())
        self.startup.setEnabled(sys.platform == "win32")
        layout.addWidget(self.startup)
        layout.addSpacing(8)
        section = QLabel("OPTIONAL AI CONNECTION")
        section.setObjectName("section")
        layout.addWidget(section)
        note = QLabel(
            "Offline mode is always available. With AI enabled, messages and recent conversation are sent to your chosen provider. No screen capture, files, or desktop control."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.provider = ProviderSelector()
        for key, (title, _, _) in PRESETS.items():
            self.provider.addItem(title, key)
        self.provider.setCurrentIndex(self.provider.findData(provider_id(settings)))
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
        discovery_row = QHBoxLayout()
        self.model_choices = QComboBox()
        self.model_choices.setMinimumContentsLength(12)
        self.model_choices.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self.model_choices.setPlaceholderText("Discover models first")
        self.model_choices.textActivated.connect(self.model.setText)
        discovery_row.addWidget(self.model_choices, 1)
        self.test_ai_button = QPushButton("Test / models")
        self.test_ai_button.setAutoDefault(False)
        discovery_row.addWidget(self.test_ai_button)
        layout.addLayout(discovery_row)
        self.test_chat = QCheckBox("Include minimal chat test (uses provider quota)")
        self.test_chat.setToolTip(
            "Sends only ‘Reply with OK.’ using the Reply tokens limit below. No private chat or conversation history is sent."
        )
        layout.addWidget(self.test_chat)
        self.share_context = QCheckBox("Include earlier chat with this provider")
        self.share_context.setToolTip(
            "Opt in to sending earlier AI conversation to a changed endpoint. Otherwise earlier messages stay visible but are excluded."
        )
        self.share_context.setChecked(False)
        layout.addWidget(self.share_context)
        self.fallback = QCheckBox("Use a clearly labeled offline reply if AI fails")
        self.fallback.setChecked(settings.get("ai_fallback"))
        layout.addWidget(self.fallback)
        response_form = QFormLayout()
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(32, 4096)
        self.max_tokens.setValue(settings.get("ai_max_tokens"))
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0, 2)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(settings.get("ai_temperature"))
        self.daily_limit = QSpinBox()
        self.daily_limit.setRange(0, 10000)
        self.daily_limit.setSpecialValueText("No app limit")
        self.daily_limit.setValue(settings.get("ai_daily_limit"))
        response_form.addRow("Reply tokens", self.max_tokens)
        response_form.addRow("Creativity", self.temperature)
        response_form.addRow("Cloud messages / day", self.daily_limit)
        layout.addLayout(response_form)
        self.remember = QCheckBox("Remember key in secure storage")
        self.remember.setToolTip(
            "Uses the operating system credential store. Keys never go in preferences."
        )
        self.remember.setChecked(companion.remember_key)
        self._saved_key = companion.key
        self._saved_remember = companion.remember_key
        layout.addWidget(self.remember)
        key_note = QLabel(
            "Keys never go in the preferences file. Uncheck and save to remove a saved key. Provider fees may apply."
        )
        key_note.setObjectName("hint")
        key_note.setWordWrap(True)
        layout.addWidget(key_note)
        self.ai_save_button = QPushButton("Save AI connection")
        self.ai_save_button.setAutoDefault(False)
        self.ai_save_button.clicked.connect(self.save_ai)
        layout.addWidget(self.ai_save_button)
        self.ai_status = QLabel(
            "Completed conversation stays until you use Clear conversation."
        )
        self.ai_status.setObjectName("hint")
        self.ai_status.setWordWrap(True)
        layout.addWidget(self.ai_status)
        self.ai_status.setTextFormat(Qt.PlainText)
        self.discovery = ProviderDiscovery(self)
        self.discovery.status.connect(self.ai_status.setText)
        self.discovery.models_found.connect(self.set_models)
        self.test_ai_button.clicked.connect(self.test_connection)
        self._profiles = deepcopy(settings.get("provider_profiles"))
        configured = settings.get("ai_provider")
        self._offline_source = configured
        if configured in ("custom", "groq", "ollama"):
            self._profiles.setdefault(
                configured,
                {"endpoint": settings.get("endpoint"), "model": settings.get("model")},
            )
        self._selection = self.provider.currentData()
        self._credential_drafts = {
            self._selection: (companion.key, companion.remember_key)
        }
        self._credential_origins = {
            self._selection: (
                companion.key,
                urlparse(settings.get("endpoint")).netloc.lower(),
            )
        }
        if configured == companion._credential_provider:
            self._credential_origins.setdefault(
                configured,
                (companion.key, urlparse(settings.get("endpoint")).netloc.lower()),
            )
        self.provider.currentIndexChanged.connect(self.choose_provider)
        self.ai_fields = (self.endpoint, self.model, self.key)
        for field in self.ai_fields:
            field.installEventFilter(self)
            field.textEdited.connect(self.discovery.cancel)
        self.features = FeatureSettings(settings)
        layout.addWidget(self.features)
        self.save_button = QPushButton("Save preferences")
        self.save_button.setObjectName("primary")
        self.save_button.setDefault(True)
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.clicked.connect(self.save)
        self.status = QLabel("")
        self.status.setObjectName("hint")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        layout.addStretch()
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        outer.addWidget(self.status)
        footer = QHBoxLayout()
        quit_button = self.quit_button = QPushButton("Quit Biscuit")
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
        self.section_nav.currentIndexChanged.connect(self.navigate_section)

    def navigate_section(self, index):
        if index < 2:
            target = self.avatar if index == 0 else self.provider
        else:
            self.features.groups.setCurrentIndex(index - 2)
            target = self.features.groups
        QTimer.singleShot(
            0,
            lambda: self.scroll.verticalScrollBar().setValue(
                max(0, target.mapTo(self.scroll.widget(), QPoint()).y() - 12)
            ),
        )

    def avatar_changed(self):
        selected = self.avatar.currentData()
        if self.name.text().strip() in ("", avatar_spec(self._draft_avatar).name):
            self.name.setText(avatar_spec(selected).name)
        self._draft_avatar = selected

    def save(self):
        try:
            if (
                sys.platform == "win32"
                and self.startup.isChecked() != startup_enabled()
            ):
                set_startup(self.startup.isChecked())
            self.settings.update(
                name=self.name.text().strip() or avatar_spec(self.avatar.currentData()).name,
                avatar=self.avatar.currentData(),
                reminders=self.reminders.isChecked(),
                chat_reactions=self.chat_reactions.isChecked(),
                scale=self.scale.value(),
                **self.features.values(),
            )
            self.status.setText("Preferences saved. Make yourself comfortable.")
            self.general_applied.emit()
        except (OSError, RuntimeError, ValueError) as exc:
            self.status.setText(str(exc))
        self.saved.emit()

    def save_ai(self):
        enabled = self.provider.isChecked()
        selected = self.provider.currentData()
        endpoint, model = (
            self.endpoint.text().strip().rstrip("/"),
            self.model.text().strip(),
        )
        key, remember = self.key.text(), self.remember.isChecked()
        try:
            if enabled:
                if not endpoint or not model:
                    raise ValueError("Enter an API base URL and model to enable AI.")
            if enabled:
                key = validate_connection(selected, endpoint, key)
                self.check_key_host(selected, endpoint, key)
            elif endpoint:
                validate_endpoint(endpoint)
            key = validate_key(key)
            changed = (
                enabled != self.settings.get("provider")
                or endpoint != self.settings.get("endpoint")
                or model != self.settings.get("model")
                or key != self._saved_key
                or selected != self.settings.get("ai_provider")
            )
            if selected != "offline":
                self._profiles[selected] = {"endpoint": endpoint, "model": model}
            self.settings.update(
                provider=enabled,
                ai_provider=selected,
                endpoint=endpoint,
                model=model,
                provider_profiles=deepcopy(self._profiles),
                ai_fallback=self.fallback.isChecked(),
                ai_max_tokens=self.max_tokens.value(),
                ai_temperature=self.temperature.value(),
                ai_daily_limit=self.daily_limit.value(),
            )
            if changed:
                self.companion.cancel_pending()
            if selected != "offline":
                self.companion.select_provider(selected)
            self.companion.select_context(endpoint, self.share_context.isChecked())
            if selected != "offline" and (
                key != self.companion.key or remember != self.companion.remember_key
            ):
                self.companion.save_key(key, remember)
            self._saved_key, self._saved_remember = key, remember
            self._credential_origins[selected] = (
                key,
                urlparse(endpoint).netloc.lower(),
            )
            self.share_context.setChecked(False)
            self.ai_status.setText(
                "AI connection saved. Your completed conversation is unchanged."
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self.ai_status.setText(str(exc))
        self.saved.emit()

    def check_key_host(self, selected, endpoint, key):
        origin_key, origin_host = self._credential_origins.get(selected, ("", ""))
        if (
            key
            and key == origin_key
            and not self.key.isModified()
            and urlparse(endpoint).netloc.lower() != origin_host
        ):
            raise ValueError(
                "The API host changed. Re-enter its API key, or clear the key for a local server, before testing or saving."
            )

    def test_connection(self):
        selected = self.provider.currentData()
        endpoint = self.endpoint.text().strip().rstrip("/")
        try:
            if selected != "offline":
                key = validate_connection(selected, endpoint, self.key.text())
                self.check_key_host(selected, endpoint, key)
            else:
                key = ""
        except ValueError as exc:
            self.ai_status.setText(str(exc))
            return
        self.discovery.discover(
            selected,
            endpoint,
            key,
            model=self.model.text(),
            test_chat=self.test_chat.isChecked(),
            temperature=self.temperature.value(),
            max_tokens=self.max_tokens.value(),
        )

    def set_models(self, models):
        self.model_choices.clear()
        self.model_choices.addItems(models)
        if not self.model.text() and models:
            self.model.setText(models[0])

    def choose_provider(self):
        self.discovery.cancel()
        old, selected = self._selection, self.provider.currentData()
        if old != "offline":
            self._profiles[old] = {
                "endpoint": self.endpoint.text(),
                "model": self.model.text(),
            }
            self._credential_drafts[old] = (self.key.text(), self.remember.isChecked())
        elif selected == self._offline_source and selected != "offline":
            # Enabling the same connection keeps edits made while it was off.
            self._profiles[selected] = {
                "endpoint": self.endpoint.text(),
                "model": self.model.text(),
            }
        if selected == "offline" and old != "offline":
            self._offline_source = old
        self._selection = selected
        self.share_context.setChecked(False)
        self.model_choices.clear()
        profile = self._profiles.get(selected)
        if selected != "offline":
            _, base, model = PRESETS[selected]
            self.endpoint.setText(profile.get("endpoint", base) if profile else base)
            self.model.setText(profile.get("model", model) if profile else model)
        if selected in self._credential_drafts:
            key, remember = self._credential_drafts[selected]
        elif selected == self.companion._credential_provider:
            key, remember = self.companion.key, self.companion.remember_key
        elif selected == "offline":
            key, remember = "", False
        else:
            try:
                key = get_secret(credential_account(selected)) or ""
            except Exception:
                key = ""
            remember = bool(key)
        self._credential_origins.setdefault(
            selected, (key, urlparse(self.endpoint.text()).netloc.lower())
        )
        self.key.setText(key)
        self.remember.setChecked(remember)
        self.ai_status.setText(
            "Offline · no AI requests."
            if selected == "offline"
            else "Local processing through Ollama. No models are downloaded by Biscuit."
            if selected == "ollama"
            else "Internet required. New messages go to this provider; earlier chat is excluded unless you opt in above."
        )

    def shutdown(self):
        self.discovery.shutdown()

    def eventFilter(self, source, event):
        if (
            source in self.ai_fields
            and event.type() == QEvent.KeyPress
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
        ):
            self.save_ai()
            return True
        return super().eventFilter(source, event)
