"""A small native trivia game; remote text is always displayed as plain text."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
)


class TriviaPage(QWidget):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        rows = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.difficulty = QComboBox()
        for key in ("easy", "medium", "hard"):
            self.difficulty.addItem(key.title(), key)
        actions.addWidget(self.difficulty)
        next_button = QPushButton("Next question")
        next_button.clicked.connect(lambda: service.next(self.difficulty.currentData()))
        actions.addWidget(next_button)
        rows.addLayout(actions)
        daily = QPushButton("Daily challenge · offline")
        daily.clicked.connect(lambda: service.next("medium", daily=True))
        rows.addWidget(daily)
        self.prompt = QLabel("A little brain break? Choose a question.")
        self.prompt.setWordWrap(True)
        self.prompt.setTextFormat(Qt.PlainText)
        rows.addWidget(self.prompt)
        self.answers = []
        self.labels = []
        for index in range(4):
            button = QPushButton()
            button.setMinimumHeight(44)
            button.setEnabled(False)
            layout = QHBoxLayout(button)
            label = QLabel("")
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(label)
            button.clicked.connect(
                lambda checked=False, number=index: service.answer(number)
            )
            self.answers.append(button)
            self.labels.append(label)
            rows.addWidget(button)
        self.status = QLabel(service.score_text())
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        rows.addWidget(self.status)
        rows.addStretch()
        attribution = QLabel(
            "Online questions: Open Trivia DB · CC BY-SA 4.0\nOffline questions: original Biscuit question bank. No account or key."
        )
        attribution.setWordWrap(True)
        attribution.setTextFormat(Qt.PlainText)
        rows.addWidget(attribution)
        service.ready.connect(self.show_question)
        service.status.connect(self.status.setText)
        service.scored.connect(self.result)

    def show_question(self, data):
        self.prompt.setText(data["question"])
        for index, (button, label, text) in enumerate(
            zip(self.answers, self.labels, data["answers"])
        ):
            label.setText(chr(65 + index) + ". " + text)
            button.setAccessibleName(text)
            button.setEnabled(not data.get("locked"))
        self.status.setText(
            data["source"]
            + " · "
            + data["score"]
            + (
                " · Daily challenge already completed today."
                if data.get("locked")
                else ""
            )
        )

    def result(self, correct, text):
        for button in self.answers:
            button.setEnabled(False)
        self.status.setText(text)
