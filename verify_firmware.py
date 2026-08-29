"""Offline validation of the supplied merged image. Does not access hardware."""
import hashlib
from pathlib import Path
import struct

EXPECTED_SHA256 = "6b81541a3cf22e9084a49408acd7c91818716f91e2fe6e5bf96bdc21d9d2e6f0"


def validate_image(blob, base):
    header = blob[base:base + 24]
    if len(header) != 24 or header[0] != 0xE9 or not 1 <= header[1] <= 16:
        raise ValueError("Invalid ESP image header")
    if header[2] != 2 or header[3] != 0x20:  # DIO, 4MB/40MHz
        raise ValueError("Unexpected flash configuration")
    if struct.unpack_from("<H", header, 12)[0] != 0:
        raise ValueError("Image is not for classic ESP32")
    position = base + 24
    checksum = 0xEF
    for _ in range(header[1]):
        address, length = struct.unpack_from("<II", blob, position)
        position += 8
        if length > len(blob) - position:
            raise ValueError("Truncated segment")
        for byte in blob[position:position + length]:
            checksum ^= byte
        position += length
    checksum_position = position | 15
    if blob[checksum_position] != checksum:
        raise ValueError("Invalid image checksum")
    end = checksum_position + 1
    if header[23] != 1 or hashlib.sha256(blob[base:end]).digest() != blob[end:end + 32]:
        raise ValueError("Invalid image SHA256")
    print("Image at 0x%x: %d segments, checksum and SHA256 OK" % (base, header[1]))


def main():
    path = Path(__file__).resolve().parent / "dist" / "pictobridge-esp32-4mb.bin"
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != EXPECTED_SHA256:
        raise ValueError("File differs from the supplied build. DO NOT FLASH.")
    validate_image(blob, 0x1000)
    validate_image(blob, 0x10000)
    partitions = []
    for offset in range(0x8000, 0x9000, 32):
        entry = blob[offset:offset + 32]
        magic = struct.unpack_from("<H", entry)[0]
        if magic == 0xEBEB:
            if entry[16:] != hashlib.md5(blob[0x8000:offset]).digest():
                raise ValueError("Invalid partition-table MD5")
            break
        if magic != 0x50AA:
            raise ValueError("Invalid partition entry")
        _, kind, subtype, start, size, label, flags = struct.unpack("<HBBII16sI", entry)
        if start + size > 4 * 1024 * 1024:
            raise ValueError("Partition exceeds 4MB")
        partitions.append((kind, subtype, start, size))
        print("Partition", label.rstrip(b"\0").decode(), hex(start), hex(size))
    else:
        raise ValueError("Missing partition-table MD5")
    if not any(kind == 0 and sub == 0 and start == 0x10000 for kind, sub, start, size in partitions):
        raise ValueError("Missing factory app partition")
    print("OK: merged image; flash offset 0x0; %d bytes" % len(blob))
    print("SHA256:", EXPECTED_SHA256)


if __name__ == "__main__":
    main()
