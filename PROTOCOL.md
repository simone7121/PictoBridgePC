# PictoBridge serial protocol v1

115200 baud, 8N1, no flow control. ASCII lines ending in LF; CR is ignored.
Boot-ROM / panic diagnostics can appear as non-protocol lines.

PC commands (prefix every line with `PB1 `):

| Command | Response | Meaning |
| --- | --- | --- |
| `HELLO` | `PB1 READY 1 MAC STARTED CLIENTS` | USB protocol ready; not proof of radio interoperability |
| `STATS` | `PB1 STATS HEAP_FREE BYTES` | Current free heap, not high-water mark |
| `INFO` | `PB1 INFO ...` | Extended firmware and session diagnostics for richer clients |
| `HELP` | `PB1 HELP ...` | Supported command summary |
| `START` | `PB1 START_REQUESTED B 7` | Starts the advertised room B on channel 7; the distributed legacy image may print A |
| `BEGIN ID` | `PB1 OK ID 0` | Start upload of exactly 10240 bitmap bytes; requires connected client |
| `DATA ID OFFSET HEX` | `PB1 OK ID NEXT_OFFSET` | Sequential 1..128 byte chunk; hex has no spaces |
| `COMMIT ID CRC32` | `PB1 QUEUED ID` | Bitmap accepted in radio queue; NOT an over-air delivery receipt |
| `ABORT` | `PB1 ABORTED` | Discard partial USB upload |

Errors: `PB1 ERROR CODE`. Do not automatically retry COMMIT after timeout.
IDs/offsets decimal; CRC32 eight hexadecimal digits, IEEE reflected CRC as
`zlib.crc32`. One upload at a time. Restart/reset clears uploads and room state.

Device events:

- `PB1 JOIN HEXNAME` / `PB1 LEAVE HEXNAME`: name bytes, UTF-16LE, padded to 20 bytes.
- `PB1 RX_BEGIN ID LENGTH MAC`
- `PB1 RX_DATA ID OFFSET HEX` repeated, up to 128 bytes per line.
- `PB1 RX_END ID CRC32`
- `PB1 WARN CODE [DETAIL]`: diagnostic/drop event.

RX messages may be interleaved with command acknowledgments at message
boundaries. Receiver must validate ID, offset, bounded length, CRC before use.
Client 0.1.1 accepts bounded RX payloads 0..10240 bytes matching the declared
length, verifies CRC, and preserves BIN+JSON. Payloads aligned to complete
1024-byte tile rows are also decoded as variable-height bitmaps for display;
the official active polygon extracted from the reference WAB/BIN is applied to
previews and newly encoded PC drawings. The original BIN is never modified or
padded. Unknown lengths are not called images.
After an RX error, remaining fragments are silently drained until a new BEGIN.
An incomplete active RX times out after 15 seconds. TX remains exactly 10240 bytes.
Palette indices 1..15 are rendered black, 0 white. No OCR, encryption or
internet transport. Firmware radio queues may drop messages under load.

The USB protocol is intentionally independent of Windows: a future Android
USB-serial client can implement it, but Android is not implemented/tested here.
