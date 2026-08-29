"""Strict serial framing, independent of the serial-port implementation."""
import time
import zlib
from pc_codec import IMAGE_BYTES


class ProtocolError(Exception):
    pass


class LineBuffer:
    def __init__(self):
        self.data = bytearray()
        self.dropping = False

    def feed(self, data):
        lines = []
        for byte in data:
            if byte == 10:
                if not self.dropping:
                    lines.append(self.data.decode("ascii", errors="replace").rstrip("\r"))
                self.data.clear()
                self.dropping = False
            elif not self.dropping:
                self.data.append(byte)
                if len(self.data) > 4096:
                    self.data.clear()
                    self.dropping = True
        return lines


class Receiver:
    def __init__(self):
        self.active = None
        self.discarding = False
        self.last_activity = 0.0

    def expire(self, timeout=15):
        if self.active is not None and time.monotonic() - self.last_activity > timeout:
            self.active = None
            self.discarding = True
            raise ProtocolError("RX incompleta: timeout; attendo un nuovo RX_BEGIN")

    def feed(self, line):
        """Validate USB payload, not its image format. Unknown formats stay raw."""
        words = line.split()
        if len(words) < 2 or words[0] != "PB1" or not words[1].startswith("RX_"):
            return None
        if self.discarding and words[1] != "RX_BEGIN":
            return None
        try:
            kind = words[1]
            if kind == "RX_BEGIN" and len(words) == 5:
                self.active = None
                ident, length = int(words[2]), int(words[3])
                if not 0 <= ident <= 0xffffffff or not 0 <= length <= IMAGE_BYTES:
                    raise ValueError("RX_BEGIN id=%s lunghezza=%s fuori limite" % (words[2], words[3]))
                if len(words[4]) != 12 or len(bytes.fromhex(words[4])) != 6:
                    raise ValueError("RX_BEGIN mittente non valido: " + words[4])
                self.active = (ident, words[4], length, bytearray())
                self.discarding = False
                self.last_activity = time.monotonic()
            elif kind == "RX_DATA" and len(words) == 5 and self.active:
                ident, sender, length, data = self.active
                if len(words[4]) > 256:
                    raise ValueError("blocco esadecimale troppo lungo: %d caratteri" % len(words[4]))
                chunk = bytes.fromhex(words[4])
                if int(words[2]) != ident or int(words[3]) != len(data):
                    raise ValueError("sequenza non valida")
                if not 0 < len(chunk) <= 128 or len(data) + len(chunk) > length:
                    raise ValueError("blocco troppo lungo")
                data.extend(chunk)
                self.last_activity = time.monotonic()
            elif kind == "RX_END" and len(words) == 4 and self.active:
                ident, sender, length, data = self.active
                self.active = None
                if int(words[2]) != ident or len(data) != length or zlib.crc32(data) != int(words[3], 16):
                    raise ValueError("lunghezza o CRC errati")
                return sender, bytes(data)
            else:
                raise ValueError("frame fuori sequenza")
        except ValueError as exc:
            self.active = None
            self.discarding = True
            raise ProtocolError(str(exc)) from exc
        return None


class Link:
    """Single-thread owner. Serial-like port has read/write and 0.1s timeout."""
    def __init__(self, port, on_line, on_image, stopped=lambda: False):
        self.port, self.on_line, self.on_image = port, on_line, on_image
        self.stopped = stopped
        self.lines = LineBuffer()
        self.receiver = Receiver()

    def write(self, command):
        data = ("PB1 " + command + "\n").encode("ascii")
        if self.port.write(data) != len(data):
            raise ProtocolError("Scrittura seriale incompleta")

    def poll(self):
        replies = []
        try:
            self.receiver.expire()
        except ProtocolError as exc:
            self.on_line(str(exc))
        for line in self.lines.feed(self.port.read(1024)):
            if line.startswith("PB1 RX_"):
                try:
                    if line.startswith("PB1 RX_BEGIN "):
                        self.on_line(line)
                    result = self.receiver.feed(line)
                    if result:
                        self.on_line("RX completa su USB: %d byte, CRC OK" % len(result[1]))
                        self.on_image(*result)
                except ProtocolError as exc:
                    detail = str(exc)
                    if line.startswith("PB1 RX_DATA "):
                        words = line.split()
                        if len(words) >= 5:
                            detail += " [riga=%d caratteri, hex=%d caratteri]" % (
                                len(line), len(words[4]))
                    self.on_line("RX scartata: " + detail)
            else:
                if not line.startswith("PB1 OK "):
                    self.on_line(line)
                replies.append(line)
        return replies

    def request(self, command, expected, timeout=5):
        self.write(command)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self.stopped():
            for line in self.poll():
                if line.startswith("PB1 ERROR "):
                    raise ProtocolError(line)
                if line == expected or line.startswith(expected + " "):
                    return line
        raise ProtocolError("Timeout: " + command.split()[0] + ". Nessuna ritrasmissione automatica.")

    def handshake(self):
        # Opening a CP210x port may transiently reset some development boards.
        last = None
        for _ in range(3):
            try:
                ready = self.request("HELLO", "PB1 READY", timeout=4)
                fields = ready.split()
                if len(fields) != 6 or fields[2] != "1":
                    raise ProtocolError("Versione firmware/protocollo non supportata")
                return ready
            except ProtocolError as exc:
                last = exc
        raise last

    def send_bitmap(self, data, ident):
        if len(data) != IMAGE_BYTES:
            raise ValueError("Bitmap di dimensione errata")
        try:
            self.request("BEGIN %d" % ident, "PB1 OK %d 0" % ident)
            for offset in range(0, len(data), 128):
                chunk = data[offset:offset + 128]
                self.request("DATA %d %d %s" % (ident, offset, chunk.hex()),
                             "PB1 OK %d %d" % (ident, offset + len(chunk)))
            self.request("COMMIT %d %08x" % (ident, zlib.crc32(data)), "PB1 QUEUED %d" % ident)
        except (ProtocolError, OSError):
            # Never retry COMMIT: it may already have reached the radio queue.
            try:
                self.request("ABORT", "PB1 ABORTED", timeout=2)
            except (ProtocolError, OSError):
                pass
            raise
