"""Modern Qt chat client for the PictoBridge serial bridge."""
import argparse
from datetime import datetime
import io
from pathlib import Path
import queue
import threading

import serial
from serial.tools import list_ports
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from pc_capture import save_capture
from pc_codec import active_x_range, decode_payload, encode, text_bitmap, test_bitmap
from pc_protocol import Link, ProtocolError


STYLE = """
* { font-family: 'Segoe UI'; }
QMainWindow, QWidget#root { background: #f4f7fb; color: #1f2937; }
QFrame#topbar { background: #14283f; }
QLabel#brand { color: #ffffff; font-size: 22px; font-weight: 700; }
QLabel#subtitle { color: #a9bed3; font-size: 11px; }
QLabel#status { color: #cfe1f3; font-size: 11px; }
QLabel#statusDot { color: #77e0a3; font-size: 17px; }
QFrame#sidebar { background: #ffffff; border-right: 1px solid #e3e9f1; }
QLabel#logo { background: #d9f5e5; color: #16734a; border-radius: 26px;
             font-size: 19px; font-weight: 700; padding: 12px; }
QLabel#sectionTitle { color: #8492a6; font-size: 10px; font-weight: 700; }
QFrame#connectionCard { background: #f5f8fc; border: 1px solid #e3e9f1;
                        border-radius: 12px; }
QLabel#connectionTitle { color: #25364b; font-weight: 600; }
QLabel#connectionMeta { color: #8190a3; font-size: 10px; }
QPushButton#primary { background: #247a52; color: white; border: 0;
                      border-radius: 8px; padding: 10px 14px; font-weight: 600; }
QPushButton#primary:hover { background: #1f6947; }
QPushButton#secondary, QToolButton#secondary { background: #edf2f7; color: #34465b;
                      border: 1px solid #dce5ef; border-radius: 8px; padding: 9px 12px; }
QPushButton#secondary:hover, QToolButton#secondary:hover { background: #e3ebf4; }
QLabel#conversationTitle { color: #21344b; font-size: 16px; font-weight: 700; }
QLabel#roomPill { background: #e1f5e8; color: #23704b; border-radius: 10px;
                  padding: 4px 9px; font-size: 10px; font-weight: 700; }
QScrollArea#chatScroll { border: 0; background: #f4f7fb; }
QWidget#chatBody { background: #f4f7fb; }
QFrame#receivedCard { background: #ffffff; border: 1px solid #e3eaf2; border-radius: 14px; }
QFrame#sentCard { background: #dff6e7; border: 1px solid #c6ead3; border-radius: 14px; }
QFrame#systemCard { background: transparent; border: 0; }
QLabel#messageName { color: #1f6c48; font-weight: 700; font-size: 11px; }
QLabel#messageTime, QLabel#messageMeta { color: #8492a4; font-size: 10px; }
QLabel#messageBody { color: #26384d; font-size: 13px; }
QLabel#messagePending { color: #7d8d9f; font-size: 10px; }
QLabel#messageFailed { color: #b55757; font-size: 10px; }
QLabel#systemText { color: #728197; font-size: 11px; }
QFrame#composer { background: #ffffff; border: 1px solid #e1e8f0; border-radius: 14px; }
QLineEdit#composerInput { background: #f7f9fc; border: 1px solid #e0e7ef;
                           border-radius: 9px; padding: 10px; color: #25364b; }
QLineEdit#composerInput:focus { border: 1px solid #4ca978; }
QToolButton#diagnosticsToggle { color: #62748a; border: 0; padding: 5px; text-align: left; }
QPlainTextEdit#diagnostics { background: #172638; color: #bed0e3; border: 0;
                             border-radius: 8px; font-family: Consolas; font-size: 10px; }
QDialog { background: #f4f7fb; }
QLabel#dialogTitle { color: #21344b; font-size: 17px; font-weight: 700; }
QLabel#dialogHint { color: #74849a; font-size: 11px; }
QComboBox#portCombo { background: #ffffff; border: 1px solid #dbe4ee; border-radius: 8px;
                      padding: 9px; color: #25364b; }
"""


DARK_STYLE = """
* { font-family: 'Segoe UI'; }
QMainWindow, QWidget#root { background: #182331; color: #e5edf5; }
QFrame#topbar { background: #0d1928; }
QLabel#brand { color: #ffffff; font-size: 22px; font-weight: 700; }
QLabel#subtitle { color: #9eb3c9; font-size: 11px; }
QLabel#status { color: #d5e3f0; font-size: 11px; }
QLabel#statusDot { color: #77e0a3; font-size: 17px; }
QFrame#sidebar { background: #202d3d; border-right: 1px solid #334356; }
QLabel#logo { background: #214d3a; color: #a9efc5; border-radius: 26px;
             font-size: 19px; font-weight: 700; padding: 12px; }
QLabel#sectionTitle { color: #9caec2; font-size: 10px; font-weight: 700; }
QFrame#connectionCard { background: #29384a; border: 1px solid #3a4b60;
                        border-radius: 12px; }
QLabel#connectionTitle { color: #edf4fa; font-weight: 600; }
QLabel#connectionMeta { color: #a9bacb; font-size: 10px; }
QPushButton#primary { background: #2d9564; color: white; border: 0;
                      border-radius: 8px; padding: 10px 14px; font-weight: 600; }
QPushButton#primary:hover { background: #3aa976; }
QPushButton#secondary, QToolButton#secondary { background: #2a3a4d; color: #dce8f2;
                      border: 1px solid #42546a; border-radius: 8px; padding: 9px 12px; }
QPushButton#secondary:hover, QToolButton#secondary:hover { background: #354961; }
QLabel#conversationTitle { color: #edf4fa; font-size: 16px; font-weight: 700; }
QLabel#roomPill { background: #214d3a; color: #a9efc5; border-radius: 10px;
                  padding: 4px 9px; font-size: 10px; font-weight: 700; }
QScrollArea#chatScroll { border: 0; background: #182331; }
QWidget#chatBody { background: #182331; }
QFrame#receivedCard { background: #263548; border: 1px solid #3a4c61; border-radius: 14px; }
QFrame#sentCard { background: #214d3a; border: 1px solid #347653; border-radius: 14px; }
QFrame#systemCard { background: transparent; border: 0; }
QLabel#messageName { color: #a9efc5; font-weight: 700; font-size: 11px; }
QLabel#messageTime, QLabel#messageMeta { color: #9db0c4; font-size: 10px; }
QLabel#messageBody { color: #edf4fa; font-size: 13px; }
QLabel#messagePending { color: #a9bacb; font-size: 10px; }
QLabel#messageFailed { color: #ffaaa5; font-size: 10px; }
QLabel#systemText { color: #9db0c4; font-size: 11px; }
QFrame#composer { background: #202d3d; border: 1px solid #3a4b60; border-radius: 14px; }
QLineEdit#composerInput { background: #29384a; border: 1px solid #42546a;
                           border-radius: 9px; padding: 10px; color: #edf4fa; }
QLineEdit#composerInput:focus { border: 1px solid #64c993; }
QToolButton#diagnosticsToggle { color: #a9bacb; border: 0; padding: 5px; text-align: left; }
QPlainTextEdit#diagnostics { background: #0d1928; color: #c2d4e6; border: 0;
                             border-radius: 8px; font-family: Consolas; font-size: 10px; }
QDialog { background: #202d3d; }
QLabel#dialogTitle { color: #edf4fa; font-size: 17px; font-weight: 700; }
QLabel#dialogHint { color: #a9bacb; font-size: 11px; }
QComboBox#portCombo { background: #29384a; border: 1px solid #42546a; border-radius: 8px;
                      padding: 9px; color: #edf4fa; }
"""


def theme_style(theme):
    return DARK_STYLE if theme == "dark" else STYLE


def theme_background(theme):
    return "#182331" if theme == "dark" else "#f4f7fb"


def timestamp():
    return datetime.now().strftime("%H:%M")


def serial_choices():
    values = []
    for info in sorted(list_ports.comports(), key=lambda item: item.device):
        parts = [info.description, info.manufacturer]
        if info.vid:
            parts.append("VID:%04X" % info.vid)
        details = " · ".join(part for part in parts if part and part != "n/a")
        values.append((info.device + (" — " + details if details else ""), info.device))
    return values


def serial_error(port_name, exc):
    text = str(exc)
    if isinstance(exc, PermissionError) or "PermissionError" in text or "Access denied" in text:
        return "Porta %s occupata o senza permessi. Chiudi l'altra GUI/terminale e riprova." % port_name
    return "Impossibile aprire %s: %s" % (port_name, text)


def user_name_from_event(line):
    """Decode the UTF-16LE name carried by PB1 JOIN/LEAVE."""
    fields = line.split()
    if len(fields) < 3 or fields[1] not in ("JOIN", "LEAVE"):
        return None
    try:
        return bytes.fromhex(fields[2]).decode("utf-16-le", errors="replace").rstrip("\0") or "DSi"
    except ValueError:
        return None


class PortDialog(QDialog):
    def __init__(self, parent=None, requested=None):
        super().__init__(parent)
        self.setWindowTitle("PictoBridge · scegli porta USB")
        self.setMinimumWidth(560)
        self.setModal(True)
        self.requested = requested
        self.mapping = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        title = QLabel("Collega l'ESP32 e scegli la porta seriale")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        hint = QLabel("Le porte vengono rilevate automaticamente. Puoi anche inserire manualmente COMx.")
        hint.setObjectName("dialogHint")
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setObjectName("portCombo")
        self.combo.setEditable(True)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(self.combo)
        refresh = QPushButton("Aggiorna")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        layout.addLayout(row)
        self.info = QLabel()
        self.info.setObjectName("dialogHint")
        layout.addWidget(self.info)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Connetti")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        buttons.accepted.connect(self.connect_port)
        buttons.rejected.connect(self.reject)
        layout.addStretch(1)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        choices = serial_choices()
        self.mapping = {label: device for label, device in choices}
        current = self.combo.currentText()
        self.combo.clear()
        self.combo.addItems([label for label, _ in choices])
        if self.requested:
            self.combo.setEditText(self.requested)
            self.requested = None
        elif current:
            self.combo.setEditText(current)
        elif choices:
            self.combo.setCurrentIndex(0)
        self.info.setText(
            "%d porta/e rilevata/e" % len(choices)
            if choices else "Nessuna porta rilevata · puoi scrivere manualmente COMx"
        )

    def connect_port(self):
        value = self.combo.currentText().strip()
        port = self.mapping.get(value, value.split(" ", 1)[0])
        if not port:
            QMessageBox.warning(self, "Porta mancante", "Seleziona o inserisci una porta seriale.")
            return
        self.selected_port = port
        self.accept()


def choose_port(parent=None, requested=None):
    if requested:
        return requested
    dialog = PortDialog(parent)
    return dialog.selected_port if dialog.exec() == QDialog.DialogCode.Accepted else None


class DrawingCanvas(QWidget):
    """Pixel-friendly 256x80 canvas, enlarged for comfortable mouse drawing."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(768, 240)
        self.image = QImage(256, 80, QImage.Format.Format_RGB32)
        self.image.fill(Qt.GlobalColor.white)
        self.last_point = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def clear(self):
        self.image.fill(Qt.GlobalColor.white)
        self.update()

    def _image_point(self, position):
        return QPointF(
            max(0, min(255, position.x() * 256 / self.width())),
            max(0, min(79, position.y() * 80 / self.height())),
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_point = self._image_point(event.position())
            self.draw_to(self.last_point, self.last_point)

    def mouseMoveEvent(self, event):
        if self.last_point is not None and event.buttons() & Qt.MouseButton.LeftButton:
            point = self._image_point(event.position())
            self.draw_to(self.last_point, point)
            self.last_point = point

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_point = None

    def draw_to(self, start, end):
        painter = QPainter(self.image)
        painter.setPen(QPen(Qt.GlobalColor.black, 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(start, end)
        painter.end()
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)
        painter.drawImage(self.rect(), self.image)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.lightGray)
        for y in range(80):
            left, right = active_x_range(y)
            top = y * 3
            if left:
                painter.drawRect(0, top, left * 3, 3)
            if right < 255:
                painter.drawRect((right + 1) * 3, top, (255 - right) * 3, 3)
        painter.setPen(QPen(Qt.GlobalColor.darkGray, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.end()

    def payload(self):
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        self.image.save(buffer, "PNG")
        image = Image.open(io.BytesIO(bytes(buffer.data()))).convert("L")
        return encode(image)


class DrawingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PictoBridge · nuovo disegno")
        self.setModal(True)
        self.setMinimumWidth(830)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        title = QLabel("Disegna un messaggio")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        hint = QLabel("Disegna nell'area 256 × 80. Il tratto verrà inviato nel formato PictoChat.")
        hint.setObjectName("dialogHint")
        layout.addWidget(hint)
        self.canvas = DrawingCanvas()
        layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        clear = QPushButton("Cancella")
        clear.setObjectName("secondary")
        clear.clicked.connect(self.canvas.clear)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        cancel = QPushButton("Annulla")
        cancel.setObjectName("secondary")
        cancel.clicked.connect(self.reject)
        use = QPushButton("Usa disegno  ➤")
        use.setObjectName("primary")
        use.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(use)
        layout.addLayout(buttons)

    def payload(self):
        return self.canvas.payload()


def run_worker(port_name, output, commands, events, stop):
    port = None

    def log(line):
        if line == "PB1 START_REQUESTED A 7":
            line += " [firmware legacy: stanza reale B]"
        if line.startswith(("PB1 JOIN ", "PB1 LEAVE ")):
            try:
                name = bytes.fromhex(line.split()[2]).decode("utf-16-le", errors="replace").rstrip("\0")
                line += " nome=" + repr(name)
            except (ValueError, IndexError):
                pass
        safe = "".join(char if char.isprintable() else repr(char)[1:-1] for char in line)
        events.put(("log", safe))

    def received(sender, payload):
        raw = png = None
        save_error = None
        try:
            raw, png = save_capture(output, sender, payload)
        except (OSError, ValueError) as exc:
            save_error = str(exc)
            log("Salvataggio ricezione fallito: " + save_error)
        events.put(("message_received", {
            "sender": sender, "length": len(payload), "raw": raw, "png": png,
            "payload": payload, "save_error": save_error,
        }))

    try:
        port = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=2)
        port.dtr = False
        port.rts = False
        port.port = port_name
        port.open()
        link = Link(port, log, received, stop.is_set)
        link.handshake()
        events.put(("ready", None))
        log("USB pronto. Premi Avvia stanza B, poi entra in B sul DSi.")
        ident = 0
        while not stop.is_set():
            try:
                command, payload, display = commands.get_nowait()
            except queue.Empty:
                link.poll()
                continue
            try:
                if command == "start":
                    link.request("START", "PB1 START_REQUESTED")
                elif command == "status":
                    link.request("HELLO", "PB1 READY")
                    link.request("STATS", "PB1 STATS")
                elif command == "send":
                    ident += 1
                    link.send_bitmap(payload, ident)
                    events.put(("message_sent", display or "Messaggio"))
                    log("Accodato sull'ESP32: verifica sul DSi la consegna.")
            except (ProtocolError, ValueError) as exc:
                log(str(exc))
                if command == "send":
                    events.put(("message_failed", display or "Messaggio"))
            finally:
                events.put(("idle", None))
    except (OSError, ProtocolError) as exc:
        log(serial_error(port_name, exc) if isinstance(exc, OSError) else str(exc))
    finally:
        if port is not None:
            port.close()
        events.put(("closed", None))


class ChatWindow(QMainWindow):
    def __init__(self, port_name, output):
        super().__init__()
        self.port_name = port_name
        self.output = output
        self.settings = QSettings("PictoBridge", "PictoBridgePC")
        self.theme = str(self.settings.value("theme", "light"))
        if self.theme not in ("light", "dark"):
            self.theme = "light"
        self.events = queue.Queue()
        self.commands = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.worker = None
        self.connected = False
        self.busy = False
        self.pending_meta = None
        self.room_started = False
        self.online_users = {}
        self.online_count_hint = 0

        self.setWindowTitle("PictoBridge · PictoChat")
        self.resize(1180, 800)
        self.setMinimumSize(900, 620)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        QApplication.instance().setStyleSheet(theme_style(self.theme))
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._topbar())

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._sidebar())
        content.addWidget(self._conversation(), 1)
        layout.addLayout(content, 1)
        self.start_worker()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_events)
        self.timer.start(50)

    def apply_theme(self, theme):
        self.theme = "dark" if theme == "dark" else "light"
        QApplication.instance().setStyleSheet(theme_style(self.theme))
        self.chat_body.setStyleSheet("background: %s;" % theme_background(self.theme))
        self.scroll.viewport().setStyleSheet("background: %s;" % theme_background(self.theme))
        self.settings.setValue("theme", self.theme)
        self.settings.sync()
        self.theme_button.setText(
            "☀   Modalità chiara" if self.theme == "dark" else "◐   Modalità scura"
        )

    def toggle_theme(self):
        self.apply_theme("dark" if self.theme == "light" else "light")

    def _topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(78)
        row = QHBoxLayout(bar)
        row.setContentsMargins(25, 13, 25, 13)
        titlebox = QVBoxLayout()
        titlebox.setSpacing(0)
        brand = QLabel("PictoBridge")
        brand.setObjectName("brand")
        subtitle = QLabel("PictoChat  ·  stanza B  ·  ESP32")
        subtitle.setObjectName("subtitle")
        titlebox.addWidget(brand)
        titlebox.addWidget(subtitle)
        row.addLayout(titlebox)
        row.addStretch(1)
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status = QLabel("Connessione a %s…" % self.port_name)
        self.status.setObjectName("status")
        row.addWidget(self.status_dot)
        row.addWidget(self.status)
        return bar

    def _sidebar(self):
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(245)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(18, 22, 18, 18)
        layout.setSpacing(12)
        logo = QLabel("PB")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(52, 52)
        layout.addWidget(logo, 0, Qt.AlignmentFlag.AlignLeft)
        section = QLabel("CONNESSIONE")
        section.setObjectName("sectionTitle")
        layout.addWidget(section)

        card = QFrame()
        card.setObjectName("connectionCard")
        cardlayout = QVBoxLayout(card)
        cardlayout.setContentsMargins(12, 11, 12, 11)
        self.connection_title = QLabel("In collegamento…")
        self.connection_title.setObjectName("connectionTitle")
        self.connection_meta = QLabel(self.port_name + "  ·  115200 baud")
        self.connection_meta.setObjectName("connectionMeta")
        cardlayout.addWidget(self.connection_title)
        cardlayout.addWidget(self.connection_meta)
        layout.addWidget(card)

        self.start_button = QPushButton("▶   Avvia stanza B")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(lambda: self.submit("start"))
        layout.addWidget(self.start_button)
        self.status_button = QPushButton("↻   Aggiorna stato")
        self.status_button.setObjectName("secondary")
        self.status_button.clicked.connect(lambda: self.submit("status"))
        layout.addWidget(self.status_button)
        self.change_button = QPushButton("⚙   Cambia porta")
        self.change_button.setObjectName("secondary")
        self.change_button.clicked.connect(self.change_port)
        layout.addWidget(self.change_button)
        users_title = QLabel("UTENTI ONLINE")
        users_title.setObjectName("sectionTitle")
        layout.addWidget(users_title)
        self.users_box = QFrame()
        self.users_box.setObjectName("connectionCard")
        self.users_layout = QVBoxLayout(self.users_box)
        self.users_layout.setContentsMargins(12, 10, 12, 10)
        self.users_layout.setSpacing(5)
        layout.addWidget(self.users_box)
        self.update_users()
        theme_title = QLabel("ASPETTO")
        theme_title.setObjectName("sectionTitle")
        layout.addWidget(theme_title)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("secondary")
        self.theme_button.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_button)
        layout.addStretch(1)
        note = QLabel("I messaggi ricevuti vengono salvati in\nricevuti/ e mostrati qui in anteprima.")
        note.setObjectName("connectionMeta")
        note.setWordWrap(True)
        layout.addWidget(note)
        return side

    def _conversation(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("Conversazione")
        title.setObjectName("conversationTitle")
        pill = QLabel("STANZA B")
        pill.setObjectName("roomPill")
        self.room_pill = pill
        header.addWidget(title)
        header.addWidget(pill)
        header.addStretch(1)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("chatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_body = QWidget()
        self.chat_body.setObjectName("chatBody")
        self.chat_body.setStyleSheet("background: #f4f7fb;")
        self.scroll.viewport().setStyleSheet("background: #f4f7fb;")
        self.chat_layout = QVBoxLayout(self.chat_body)
        self.chat_layout.setContentsMargins(4, 4, 4, 4)
        self.chat_layout.setSpacing(9)
        self.chat_layout.addStretch(1)
        self.scroll.setWidget(self.chat_body)
        self.scroll.verticalScrollBar().rangeChanged.connect(
            lambda _minimum, _maximum: self.scroll_to_bottom()
        )
        layout.addWidget(self.scroll, 1)
        self.add_system("In attesa del collegamento USB…")

        composer = QFrame()
        composer.setObjectName("composer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(10, 8, 10, 8)
        self.input = QLineEdit()
        self.input.setObjectName("composerInput")
        self.input.setPlaceholderText("Scrivi un messaggio per PictoChat…")
        self.input.returnPressed.connect(self.send_text)
        composer_layout.addWidget(self.input, 1)
        self.test_button = QPushButton("Disegno test")
        self.test_button.setObjectName("secondary")
        self.test_button.clicked.connect(lambda: self.submit("send", True))
        composer_layout.addWidget(self.test_button)
        self.draw_button = QPushButton("Disegna")
        self.draw_button.setObjectName("secondary")
        self.draw_button.clicked.connect(self.open_drawing)
        composer_layout.addWidget(self.draw_button)
        self.send_button = QPushButton("Invia  ➤")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.send_text)
        composer_layout.addWidget(self.send_button)
        layout.addWidget(composer)

        toggle = QToolButton()
        toggle.setObjectName("diagnosticsToggle")
        toggle.setText("⌄  Diagnostica seriale")
        toggle.setCheckable(True)
        toggle.toggled.connect(self.toggle_diagnostics)
        layout.addWidget(toggle)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setObjectName("diagnostics")
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumHeight(125)
        self.diagnostics.setVisible(False)
        layout.addWidget(self.diagnostics)
        self.theme_button.setText(
            "☀   Modalità chiara" if self.theme == "dark" else "◐   Modalità scura"
        )
        return panel

    def start_worker(self):
        # Each connection gets fresh queues. Events from a crashed/old worker
        # must never overwrite the state of the newly selected port.
        self.events = queue.Queue()
        self.commands = queue.Queue(maxsize=1)
        self.pending_meta = None
        self.stop = threading.Event()
        self.worker = threading.Thread(
            target=run_worker,
            args=(self.port_name, self.output, self.commands, self.events, self.stop),
            daemon=True,
        )
        self.worker.start()

    def stop_worker(self):
        self.stop.set()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=1.0)

    def change_port(self):
        if self.busy:
            return
        self.stop_worker()
        self.connected = False
        self.room_started = False
        self.online_users.clear()
        self.online_count_hint = 0
        self.update_users()
        self.update_controls()
        port = choose_port(self, self.port_name)
        if not port:
            self.status.setText("Nessuna porta selezionata")
            self.connection_title.setText("Disconnesso")
            return
        self.port_name = port
        self.connection_meta.setText(self.port_name + "  ·  115200 baud")
        self.status.setText("Connessione a %s…" % self.port_name)
        self.add_system("Cambio porta: %s" % self.port_name)
        self.start_worker()

    def toggle_diagnostics(self, visible):
        self.diagnostics.setVisible(visible)

    def send_text(self):
        self.submit("send")

    def open_drawing(self):
        if not self.connected or self.busy:
            return
        dialog = DrawingDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            payload = dialog.payload()
            self.queue_payload(payload, "Disegno personale", self.pixmap_from_payload(payload))

    def submit(self, command, pattern=False):
        if not self.connected or self.busy:
            return
        try:
            if command == "send":
                display = "Disegno test" if pattern else self.input.text().strip()
                payload = test_bitmap() if pattern else text_bitmap(display)
                preview = self.pixmap_from_payload(payload) if pattern else None
                self.queue_payload(payload, display, preview)
                return
            else:
                payload, display = None, None
            self.commands.put_nowait((command, payload, display))
            self.busy = True
            self.status.setText("Operazione in corso…")
            self.update_controls()
        except (ValueError, queue.Full) as exc:
            self.add_system(str(exc))

    def queue_payload(self, payload, display, pixmap=None):
        try:
            self.commands.put_nowait(("send", payload, display))
            self.busy = True
            self.pending_meta = self.add_message(
                "sent", "Tu", body=display, meta="invio in corso…", pixmap=pixmap
            )
            if self.pending_meta:
                self.pending_meta.setObjectName("messagePending")
                self.pending_meta.setStyleSheet("color: #7d8d9f; font-size: 10px;")
            self.status.setText("Invio in corso…")
            self.update_controls()
        except queue.Full:
            self.add_system("Trasferimento occupato; attendi la fine dell'invio.")

    def update_controls(self):
        enabled = self.connected and not self.busy
        for button in (self.status_button, self.test_button, self.draw_button, self.send_button):
            button.setEnabled(enabled)
        self.start_button.setEnabled(enabled and not self.room_started)
        self.change_button.setEnabled(not self.busy)
        if self.room_started:
            count = len(self.online_users) or self.online_count_hint
            self.start_button.setText("✓   Stanza B attiva%s" % (
                " · %d online" % count if count else ""
            ))
        else:
            self.start_button.setText("▶   Avvia stanza B")

    def refresh_status(self):
        if not self.connected:
            return
        count = len(self.online_users) or self.online_count_hint
        if self.room_started:
            self.status.setText("Connesso · stanza B · %d online" % count)
        else:
            self.status.setText("Connesso · %s" % self.port_name)

    def update_users(self):
        while self.users_layout.count():
            item = self.users_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.online_users:
            empty = QLabel("Nessun DSi online")
            empty.setObjectName("connectionMeta")
            self.users_layout.addWidget(empty)
        else:
            for name in self.online_users:
                user = QLabel("●   %s" % name)
                user.setObjectName("connectionTitle")
                self.users_layout.addWidget(user)
        if hasattr(self, "room_pill"):
            count = len(self.online_users) or self.online_count_hint
            self.room_pill.setText("%d ONLINE" % count if count else "STANZA B")
        if hasattr(self, "start_button") and hasattr(self, "test_button"):
            self.update_controls()

    def handle_membership(self, line):
        fields = line.split()
        if len(fields) < 2 or fields[1] not in ("JOIN", "LEAVE"):
            return False
        name = user_name_from_event(line) or "DSi"
        if fields[1] == "JOIN":
            self.online_users[name] = name
            self.room_started = True
            self.add_system("%s è online" % name)
        else:
            self.online_users.pop(name, None)
            self.add_system("%s è offline" % name)
        self.update_users()
        self.refresh_status()
        return True

    def received_name(self, sender):
        # The current firmware sends JOIN with the console name and RX_BEGIN
        # with the MAC. With one DSi (the supported prototype use case), this
        # safely associates the incoming payload with the only online name.
        if len(self.online_users) == 1:
            return next(iter(self.online_users))
        return "DSi · " + sender

    def add_system(self, text):
        card = QFrame()
        card.setObjectName("systemCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(8, 2, 8, 2)
        label = QLabel("%s   %s" % (timestamp(), text))
        label.setObjectName("systemText")
        label.setWordWrap(True)
        row.addWidget(label)
        row.addStretch(1)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, card)
        self.scroll_to_bottom()

    def add_message(self, side, name, body=None, meta=None, pixmap=None):
        row = QHBoxLayout()
        row.setContentsMargins(8, 2, 8, 2)
        card = QFrame()
        card.setObjectName("sentCard" if side == "sent" else "receivedCard")
        card.setMaximumWidth(760)
        inner = QVBoxLayout(card)
        inner.setContentsMargins(15, 11, 15, 11)
        inner.setSpacing(5)
        top = QHBoxLayout()
        name_label = QLabel(name)
        name_label.setObjectName("messageName")
        time_label = QLabel(timestamp())
        time_label.setObjectName("messageTime")
        top.addWidget(name_label)
        top.addStretch(1)
        top.addWidget(time_label)
        inner.addLayout(top)
        if body:
            body_label = QLabel(body)
            body_label.setObjectName("messageBody")
            body_label.setWordWrap(True)
            inner.addWidget(body_label)
        if pixmap and not pixmap.isNull():
            image = QLabel()
            image.setPixmap(pixmap)
            image.setAlignment(Qt.AlignmentFlag.AlignLeft)
            image.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            inner.addWidget(image)
        meta_label = None
        if meta:
            meta_label = QLabel(meta)
            meta_label.setObjectName("messageMeta")
            meta_label.setWordWrap(True)
            inner.addWidget(meta_label)
        if side == "sent":
            row.addStretch(1)
            row.addWidget(card)
        else:
            row.addWidget(card)
            row.addStretch(1)
        container = QWidget()
        container.setLayout(row)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, container)
        self.scroll_to_bottom()
        return meta_label

    def pixmap_from_payload(self, payload):
        try:
            image, height = decode_payload(payload)
            image = image.convert("RGB").resize(
                (image.width * 3, height * 3), Image.Resampling.NEAREST
            )
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue(), "PNG")
            return pixmap
        except (ValueError, OSError):
            return QPixmap()

    def pixmap_for_received(self, data):
        png = data.get("png")
        pixmap = QPixmap(str(png)) if png else QPixmap()
        if pixmap.isNull():
            pixmap = self.pixmap_from_payload(data.get("payload", b""))
        if pixmap.width() > 700:
            pixmap = pixmap.scaledToWidth(700, Qt.TransformationMode.FastTransformation)
        return pixmap

    def show_received(self, data):
        pixmap = self.pixmap_for_received(data)
        raw = data.get("raw")
        if not pixmap.isNull():
            if raw:
                meta = "%d byte  ·  salvato in %s" % (data["length"], raw)
            else:
                meta = "%d byte  ·  anteprima dal payload" % data["length"]
            self.add_message("received", "DSi  ·  " + self.received_name(data["sender"]),
                             meta=meta, pixmap=pixmap)
            return
        meta = "BIN/JSON: %s" % raw if raw else "Salvataggio locale non riuscito"
        if data.get("save_error"):
            meta += "  ·  " + data["save_error"]
        self.add_message("received", "DSi  ·  " + self.received_name(data["sender"]),
                         body="Payload ricevuto (%d byte)" % data["length"], meta=meta)

    def scroll_to_bottom(self):
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def poll_events(self):
        for _ in range(100):
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.diagnostics.appendPlainText(timestamp() + "  " + data)
                if data.startswith("PB1 JOIN ") or data.startswith("PB1 LEAVE "):
                    self.handle_membership(data)
                elif data.startswith("PB1 READY "):
                    fields = data.split()
                    if len(fields) >= 6:
                        self.room_started = fields[4] == "1"
                        try:
                            self.online_count_hint = int(fields[5])
                        except ValueError:
                            self.online_count_hint = 0
                    self.add_system(data)
                    self.update_users()
                    self.refresh_status()
                elif data.startswith("PB1 START_REQUESTED"):
                    self.room_started = True
                    self.add_system("Stanza B attiva · in attesa dei DSi")
                    self.update_controls()
                    self.refresh_status()
                elif data.startswith(("PB1 RX_BEGIN", "PB1 ERROR", "PB1 WARN", "RX completa",
                                      "RX scartata", "Connessione interrotta", "Porta ")):
                    self.add_system(data)
            elif kind == "message_sent":
                if self.pending_meta:
                    self.pending_meta.setText("accodato nella coda radio")
                    self.pending_meta.setStyleSheet("color: #4e8b69; font-size: 10px;")
                    self.pending_meta = None
                else:
                    self.add_message("sent", "Tu", body=data, meta="accodato nella coda radio")
                self.input.clear()
            elif kind == "message_failed":
                if self.pending_meta:
                    self.pending_meta.setText("invio fallito")
                    self.pending_meta.setStyleSheet("color: #b55757; font-size: 10px;")
                    self.pending_meta = None
            elif kind == "message_received":
                self.show_received(data)
            elif kind == "ready":
                self.connected = True
                self.status_dot.setStyleSheet("color: #77e0a3; font-size: 17px;")
                self.refresh_status()
                self.connection_title.setText("ESP32 connesso")
                self.update_controls()
            elif kind == "idle":
                self.busy = False
                self.refresh_status()
                self.update_controls()
            elif kind == "closed":
                self.connected = False
                self.busy = False
                self.status_dot.setStyleSheet("color: #f0a36b; font-size: 17px;")
                self.status.setText("Disconnesso · usa Cambia porta per riprovare")
                self.connection_title.setText("Disconnesso")
                self.update_controls()

    def closeEvent(self, event):
        self.stop_worker()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="PictoBridge PC Qt chat GUI")
    parser.add_argument("--port", default=None, help="porta seriale; se omessa viene mostrato il selettore")
    parser.add_argument("--output", type=Path, default=Path("ricevuti"))
    args = parser.parse_args()
    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    port = choose_port(None, args.port)
    if not port:
        return 0
    window = ChatWindow(port, args.output)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
