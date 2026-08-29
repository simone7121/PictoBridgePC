import unittest
import zlib
import tempfile
from pathlib import Path
import json
from PIL import Image
from pc_codec import (IMAGE_BYTES, TILE_ROW_BYTES, active_pixel, decode,
                      decode_payload, encode, payload_height, pixel_address,
                      test_bitmap, text_bitmap)
from pc_protocol import LineBuffer, Receiver, Link, ProtocolError
from pc_capture import save_capture


class CodecTests(unittest.TestCase):
    def test_known_addresses(self):
        self.assertEqual(pixel_address(0, 0), (0, 0))
        self.assertEqual(pixel_address(1, 0), (0, 4))
        self.assertEqual(pixel_address(0, 1), (4, 0))
        self.assertEqual(pixel_address(8, 0), (32, 0))
        self.assertEqual(pixel_address(0, 8), (1024, 0))
        self.assertEqual(pixel_address(255, 79), (10239, 4))

    def test_pixels_roundtrip(self):
        image = Image.new("L", (256, 80), 255)
        for point in ((0, 0), (1, 0), (8, 0), (0, 8), (255, 79), (113, 51)):
            image.putpixel(point, 0)
        encoded = encode(image)
        self.assertEqual(encoded[0], 0x11)
        self.assertEqual(encoded[-1], 0x10)
        self.assertEqual(decode(encoded).tobytes(), image.tobytes())

    def test_official_active_boundary_clips_transmit_bitmap(self):
        image = Image.new("L", (256, 80), 0)
        encoded = encode(image, clip=True)
        decoded = decode(encoded)
        self.assertTrue(active_pixel(24, 16))
        self.assertTrue(active_pixel(251, 79))
        self.assertFalse(active_pixel(23, 16))
        self.assertFalse(active_pixel(80, 0))
        self.assertEqual(decoded.getpixel((24, 16)), 0)
        self.assertEqual(decoded.getpixel((23, 16)), 255)
        self.assertEqual(decoded.getpixel((80, 0)), 255)

    def test_text_and_pattern(self):
        for data in (text_bitmap("Ciao Simone!"), test_bitmap()):
            self.assertEqual(len(data), IMAGE_BYTES)
            self.assertTrue(any(data))
            self.assertEqual(encode(decode(data)), data)

    def test_invalid_length(self):
        with self.assertRaises(ValueError):
            decode(b"\0")
        with self.assertRaises(ValueError):
            text_bitmap("x" * 1000)

    def test_variable_height_payloads(self):
        for rows in (2, 8, 10):
            data = test_bitmap()[:rows * TILE_ROW_BYTES]
            self.assertEqual(payload_height(data), rows * 8)
            image, height = decode_payload(data)
            self.assertEqual(image.size, (256, rows * 8))
            self.assertEqual(height, rows * 8)

        with self.assertRaises(ValueError):
            decode_payload(b"x" * 100)


class FramingTests(unittest.TestCase):
    def test_fragmented_lines(self):
        buffer = LineBuffer()
        self.assertEqual(buffer.feed(b"PB1 REA"), [])
        self.assertEqual(buffer.feed(b"DY\r\nPB1 B"), ["PB1 READY"])
        self.assertEqual(buffer.feed(b"OOT\n"), ["PB1 BOOT"])

    def test_overflow_recovers_at_newline(self):
        buffer = LineBuffer()
        self.assertEqual(buffer.feed(b"x" * 4097 + b"\nPB1 OK\n"), ["PB1 OK"])

    def test_reassembly(self):
        receiver = Receiver()
        data = test_bitmap()
        receiver.feed("PB1 RX_BEGIN 1 10240 aabbccddeeff")
        for offset in range(0, len(data), 128):
            receiver.feed("PB1 RX_DATA 1 %d %s" % (offset, data[offset:offset+128].hex()))
        result = receiver.feed("PB1 RX_END 1 %08x" % zlib.crc32(data))
        self.assertEqual(result, ("aabbccddeeff", data))

    def test_bad_order_and_size(self):
        receiver = Receiver()
        with self.assertRaises(ProtocolError):
            receiver.feed("PB1 RX_BEGIN 1 999999 aabbccddeeff")
        self.assertIsNone(receiver.feed("PB1 RX_DATA 1 0 aa"))
        receiver.feed("PB1 RX_BEGIN 1 10240 aabbccddeeff")
        with self.assertRaises(ProtocolError):
            receiver.feed("PB1 RX_DATA 1 10 aa")
        self.assertIsNone(receiver.active)

    def test_incomplete_end_rejected(self):
        receiver = Receiver()
        receiver.feed("PB1 RX_BEGIN 1 10240 aabbccddeeff")
        with self.assertRaises(ProtocolError):
            receiver.feed("PB1 RX_END 1 00000000")

    def test_short_payload_preserved_and_crc_checked(self):
        receiver = Receiver()
        data = b"unknown-format" * 20
        receiver.feed("PB1 RX_BEGIN 9 %d aabbccddeeff" % len(data))
        for offset in range(0, len(data), 128):
            receiver.feed("PB1 RX_DATA 9 %d %s" % (offset, data[offset:offset+128].hex()))
        self.assertEqual(receiver.feed("PB1 RX_END 9 %08x" % zlib.crc32(data)), ("aabbccddeeff", data))

    def test_oversized_rx_chunk_reports_clear_error(self):
        receiver = Receiver()
        receiver.feed("PB1 RX_BEGIN 11 128 aabbccddeeff")
        with self.assertRaisesRegex(ProtocolError, "blocco esadecimale troppo lungo"):
            receiver.feed("PB1 RX_DATA 11 0 " + "aa" * 129)

    def test_crc_failure_suppressed_until_next_begin(self):
        receiver = Receiver()
        receiver.feed("PB1 RX_BEGIN 9 1 aabbccddeeff")
        receiver.feed("PB1 RX_DATA 9 0 aa")
        with self.assertRaises(ProtocolError):
            receiver.feed("PB1 RX_END 9 00000000")
        for _ in range(20):
            self.assertIsNone(receiver.feed("PB1 RX_DATA 9 1 aa"))
        receiver.feed("PB1 RX_BEGIN 10 0 aabbccddeeff")
        self.assertEqual(receiver.feed("PB1 RX_END 10 00000000"), ("aabbccddeeff", b""))

    def test_bad_sender_and_expiration(self):
        receiver = Receiver()
        with self.assertRaises(ProtocolError):
            receiver.feed("PB1 RX_BEGIN 1 3 badmac")
        receiver.feed("PB1 RX_BEGIN 1 3 aabbccddeeff")
        receiver.last_activity = 0
        with self.assertRaises(ProtocolError):
            receiver.expire()
        self.assertIsNone(receiver.feed("PB1 RX_END 1 00000000"))


class CaptureTests(unittest.TestCase):
    def test_unknown_payload_stays_exact_no_fake_png(self):
        with tempfile.TemporaryDirectory() as directory:
            data = b"test-data" * 17
            raw, png = save_capture(directory, "aabbccddeeff", data)
            self.assertEqual(raw.read_bytes(), data)
            self.assertIsNone(png)
            meta = json.loads(raw.with_suffix(".json").read_text())
            self.assertEqual(meta["length"], len(data))
            self.assertEqual(meta["format"], "unknown")

    def test_full_bitmap_saves_raw_and_png(self):
        with tempfile.TemporaryDirectory() as directory:
            raw, png = save_capture(directory, "aabbccddeeff", test_bitmap())
            self.assertEqual(len(raw.read_bytes()), IMAGE_BYTES)
            with Image.open(png) as image:
                self.assertEqual(image.size, (768, 240))

    def test_variable_bitmap_saves_cropped_png(self):
        with tempfile.TemporaryDirectory() as directory:
            data = test_bitmap()[:2 * TILE_ROW_BYTES]
            raw, png = save_capture(directory, "aabbccddeeff", data)
            self.assertEqual(raw.read_bytes(), data)
            with Image.open(png) as image:
                self.assertEqual(image.size, (768, 48))
            meta = json.loads(raw.with_suffix(".json").read_text())
            self.assertEqual(meta["format"], "4bpp_256x16_bounded")


class FakePort:
    """Only a transport simulation. It does not emulate a Nintendo radio."""
    def __init__(self, fail_commit=False):
        self.rx = bytearray()
        self.data = bytearray()
        self.commands = []
        self.fail_commit = fail_commit

    def write(self, data):
        words = data.decode().split()
        self.commands.append(words[1])
        if words[1] == "HELLO":
            reply = "PB1 READY 1 aabbccddeeff 0 0"
        elif words[1] == "BEGIN":
            self.data.clear()
            reply = "PB1 OK %s 0" % words[2]
        elif words[1] == "DATA":
            if int(words[3]) != len(self.data):
                raise AssertionError("bad offset")
            self.data.extend(bytes.fromhex(words[4]))
            reply = "PB1 OK %s %d" % (words[2], len(self.data))
        elif words[1] == "COMMIT":
            if zlib.crc32(self.data) != int(words[3], 16):
                raise AssertionError("bad checksum")
            reply = "PB1 ERROR RADIO_BUSY" if self.fail_commit else "PB1 QUEUED " + words[2]
        elif words[1] == "ABORT":
            reply = "PB1 ABORTED"
        else:
            raise AssertionError("unexpected command")
        self.rx.extend((reply + "\n").encode())
        return len(data)

    def read(self, size):
        chunk = bytes(self.rx[:7])  # deliberately fragmented frames
        del self.rx[:7]
        return chunk


class TransportTests(unittest.TestCase):
    def test_handshake_and_upload(self):
        port = FakePort()
        link = Link(port, lambda s: None, lambda m, d: None)
        link.handshake()
        data = test_bitmap()
        link.send_bitmap(data, 7)
        self.assertEqual(port.data, data)
        self.assertEqual(port.commands.count("DATA"), 80)
        self.assertEqual(port.commands.count("COMMIT"), 1)

    def test_error_aborts_without_commit_retry(self):
        port = FakePort(fail_commit=True)
        link = Link(port, lambda s: None, lambda m, d: None)
        with self.assertRaises(ProtocolError):
            link.send_bitmap(test_bitmap(), 8)
        self.assertEqual(port.commands.count("COMMIT"), 1)
        self.assertEqual(port.commands[-1], "ABORT")


if __name__ == "__main__":
    unittest.main()
