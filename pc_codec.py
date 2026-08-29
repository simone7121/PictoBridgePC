"""PictoChat 256x80, 8x8 tiles, low nibble first. Initial B/W renderer."""
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 256, 80
IMAGE_BYTES = WIDTH * HEIGHT // 2
TILE_ROW_BYTES = WIDTH * 8 // 2

# Official active drawing boundary extracted from the supplied complete WAB/BIN
# capture (SHA256 7fae97fbabd64672556a876b9b4710bffc615d9bd401a2e670ff804b451163a7).
# The isolated white pixel at (48, 16) is treated as a capture artefact: the
# active area is a continuous polygon for encoding and display.
ACTIVE_BIN_SHA256 = "7fae97fbabd64672556a876b9b4710bffc615d9bd401a2e670ff804b451163a7"


def active_x_range(y):
    """Return the inclusive active x range for one 256x80 bitmap row."""
    if not 0 <= y < HEIGHT:
        return None
    if y == 0:
        return 81, 250
    if y == 1:
        return 82, 251
    if y < 16:
        return 81, 251
    return 24, 251


def active_pixel(x, y):
    """Whether a pixel is inside the official DSi drawing polygon."""
    row = active_x_range(y)
    return row is not None and row[0] <= x <= row[1]


def pixel_address(x, y):
    pixel = ((y // 8) * 32 + x // 8) * 64 + (y % 8) * 8 + x % 8
    return pixel // 2, (pixel % 2) * 4


def encode(image, clip=False):
    if image.size != (WIDTH, HEIGHT):
        raise ValueError("L'immagine deve essere 256x80 pixel.")
    pixels = image.convert("L").load()
    data = bytearray(IMAGE_BYTES)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if pixels[x, y] < 128 and (not clip or active_pixel(x, y)):
                index, shift = pixel_address(x, y)
                data[index] |= 1 << shift
    return bytes(data)


def decode(data):
    if len(data) != IMAGE_BYTES:
        raise ValueError("Bitmap incompleta/non supportata: %d byte" % len(data))
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    pixels = image.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            index, shift = pixel_address(x, y)
            # Rainbow colours are deliberately rendered black in v0.1.
            if (data[index] >> shift) & 15:
                pixels[x, y] = 0
    return image


def payload_height(data):
    """Return the inferred height for a complete-width variable-height payload.

    PictoChat captures in this project have been observed at 2048, 8192 and
    10240 bytes. These are complete 256-pixel tile rows (1024 bytes each).
    This inference is deliberately limited to aligned sizes; arbitrary data is
    still kept as raw bytes and is not interpreted as an image.
    """
    if not data or len(data) > IMAGE_BYTES or len(data) % TILE_ROW_BYTES:
        return None
    return len(data) * 2 // WIDTH


def decode_payload(data):
    """Decode a full or aligned variable-height payload.

    Missing rows are treated as white only for rendering. The original bytes
    remain unchanged in the capture saved by pc_capture.py.
    """
    height = payload_height(data)
    if height is None:
        raise ValueError("Payload non allineato/non supportato: %d byte" % len(data))
    padded = data + b"\0" * (IMAGE_BYTES - len(data))
    image = decode(padded)
    if height:
        pixels = image.load()
        for y in range(height):
            row = active_x_range(y)
            for x in range(WIDTH):
                if row[0] > x or x > row[1]:
                    pixels[x, y] = 255
    return image.crop((0, 0, WIDTH, height)), height


def text_bitmap(text):
    if not text.strip():
        raise ValueError("Scrivi un messaggio non vuoto.")
    font = ImageFont.load_default(size=12)
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for char in paragraph:
            if draw.textlength(line + char, font=font) > WIDTH - 8:
                lines.append(line)
                line = ""
            line += char
        lines.append(line)
    if len(lines) > 4:
        raise ValueError("Testo troppo lungo: massimo 4 righe nell'area DSi.")
    for i, line in enumerate(lines):
        draw.text((28, 18 + i * 15), line, fill=0, font=font)
    return encode(image, clip=True)


def test_bitmap():
    image = Image.new("L", (WIDTH, HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 255, 79), outline=0)
    draw.rectangle((3, 3, 14, 14), fill=0)
    draw.line((0, 79, 255, 0), fill=0)
    draw.text((24, 20), "PictoPC - test 256 x 80", fill=0, font=ImageFont.load_default(size=12))
    draw.rectangle((239, 62, 252, 76), outline=0)
    return encode(image, clip=True)
