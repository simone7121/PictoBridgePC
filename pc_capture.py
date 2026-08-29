"""Lossless local diagnostic capture; do not invent pixels for unknown formats."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid
import zlib
from pc_codec import decode_payload, payload_height


def save_capture(directory, sender, payload):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    height = payload_height(payload)
    stem = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex
    base = directory / stem
    raw = base.with_suffix(".bin")
    with raw.open("xb") as target:
        target.write(payload)
    metadata = {
        "client_version": "0.1.1", "sender": sender, "length": len(payload),
        "usb_crc32": "%08x" % zlib.crc32(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "utc": datetime.now(timezone.utc).isoformat(),
        "format": ("4bpp_256x%d_bounded" % height) if height is not None else "unknown",
        "note": "CRC verifies USB transfer only; radio reassembly not independently verified.",
    }
    with base.with_suffix(".json").open("x", encoding="utf-8") as target:
        json.dump(metadata, target, indent=2)
    png = None
    if height is not None:
        png = base.with_suffix(".png")
        with png.open("xb") as target:
            image, height = decode_payload(payload)
            image.resize((768, height * 3), resample=0).save(target, format="PNG")
    return raw.resolve(), png.resolve() if png else None
