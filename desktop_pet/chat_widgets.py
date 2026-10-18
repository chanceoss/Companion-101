"""Native message bubbles: plain text, selection, avatars, timestamps, and scrolling."""
import math
from PySide6.QtCore import Qt, QRectF, QDateTime, QTimer, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QTextOption
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                               QTextBrowser, QVBoxLayout, QWidget)
from .theme import garden, paw, ui_font


class Avatar(QWidget):
    def __init__(self, sprite, mine=False):
        super().__init__()
        self.sprite, self.mine = sprite, mine
        self.setFixedSize(42, 42)
        self.setAccessibleName("Your avatar" if mine else "Biscuit avatar")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#edf1e2" if self.mine else "#ffedc9"))
        p.drawEllipse(self.rect())
        clip = QPainterPath()
        clip.addEllipse(QRectF(self.rect()))
        p.setClipPath(clip)
        if self.mine:
            paw(p, 10, 10, 22, "#a2b382")
        else:
            p.drawPixmap(QRectF(0, 0, 42, 42), self.sprite, QRectF(92, 14, 290, 280))


class BubbleText(QTextBrowser):
    def __init__(self, text):
        super().__init__()
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFont(ui_font(16))
        self.setStyleSheet("QTextBrowser {background: transparent; border: 0; padding: 0; color: #684635; font-size: 17px; selection-background-color: #e7d1ae;}")
        self.document().setDocumentMargin(0)
        self.setPlainText(text)
        self.setAccessibleName("Message")
        self.document().documentLayout().documentSizeChanged.connect(self.fit_height)

    def fit_height(self, *args):
        height = max(26, math.ceil(self.document().size().height()) + 4)
        if height != self.height():
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.document().setTextWidth(max(20, self.viewport().width()))
        self.fit_height()


class Message(QWidget):
    def __init__(self, who, text, sprite, mine=False, error=False):
        super().__init__()
        self.setMinimumWidth(0)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(Avatar(sprite, mine), alignment=Qt.AlignTop)
        content = QVBoxLayout()
        content.setSpacing(8)
        title_row = QHBoxLayout()
        author = QLabel(who)
        author.setTextFormat(Qt.PlainText)
        author.setFont(ui_font(16, weight=700))
        author.setStyleSheet("color: #8c4b26;" if not mine else "color: #7f9168;")
        title_row.addWidget(author)
        timestamp = QLabel(QDateTime.currentDateTime().toString("h:mm AP"))
        timestamp.setFont(ui_font(12))
        timestamp.setStyleSheet("color: #b49c8c;")
        title_row.addWidget(timestamp)
        title_row.addStretch()
        content.addLayout(title_row)
        bubble = QFrame()
        fill, border = ("#fff4e1", "#fae9d1") if not mine else ("#eef3e5", "#dfe8ce")
        if error:
            fill, border = "#fff0e9", "#efc5b3"
        bubble.setStyleSheet(f"QFrame {{background: {fill}; border: 1px solid {border}; border-radius: 17px;}}")
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(16, 12, 16, 12)
        text_widget = BubbleText(text)
        bubble_layout.addWidget(text_widget)
        if "\n" not in text and len(text) < 60:
            bubble.setMaximumWidth(max(160, text_widget.fontMetrics().horizontalAdvance(text) + 38))
            content.addWidget(bubble, alignment=Qt.AlignLeft)
        else:
            content.addWidget(bubble)
        row.addLayout(content, 1)
        # Keep short messages cozy while letting long messages wrap with the pane.
        row.addSpacing(20 if not mine else 0)


class ChatHistory(QScrollArea):
    def minimumSizeHint(self):
        return QSize(0, 40)

    def __init__(self, sprites):
        super().__init__()
        self.sprites = sprites
        self.messages = []
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget {background: transparent; border: 0;}")
        self.viewport().setAutoFillBackground(False)
        self.content = QWidget()
        self.content.setAutoFillBackground(False)
        self.content.setMinimumWidth(0)
        self.rows = QVBoxLayout(self.content)
        self.rows.setContentsMargins(20, 24, 18, 110)
        self.rows.setSpacing(24)
        self.rows.setAlignment(Qt.AlignTop)
        self.setWidget(self.content)
        self.setAccessibleName("Conversation")
        self.verticalScrollBar().rangeChanged.connect(self.scroll_to_bottom)

    def add_message(self, who, message, mine=False, error=False):
        self.messages.append((who, message))
        self.rows.addWidget(Message(who, message, self.sprites.frame("idle", 0), mine, error))
        QTimer.singleShot(0, self.scroll_to_bottom)

    def scroll_to_bottom(self, *args):
        self.verticalScrollBar().setValue(0 if len(self.messages) <= 1 else self.verticalScrollBar().maximum())

    def toPlainText(self):
        return "\n\n".join(f"{who}\n{text}" for who, text in self.messages)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.rows.setContentsMargins(16, 16, 14, max(12, min(110, self.viewport().height() // 5)))

    def clear(self):
        self.messages.clear()
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()


class ConversationFrame(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 18, 18)
        p.fillPath(path, QColor("#fffefd"))
        p.setClipPath(path)
        garden(p, QRectF(self.rect()), corner=True)
        paw(p, self.width() - 40, self.height() * .57, 20, "#f7e6d1", -13)
        paw(p, self.width() - 46, self.height() * .77, 19, "#f7e6d1", 17)
        p.setClipping(False)
        p.setPen(QColor("#ebded2"))
        p.drawPath(path)
