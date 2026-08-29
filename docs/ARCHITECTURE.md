# Architecture and data flow

PictoBridgePC has three layers:

```text
PySide6 GUI / terminal client
            │  USB UART, 115200 8N1
            ▼
      ESP32 bridge firmware
            │  FoA + foa_dswifi
            ▼
       Nintendo DSi PictoChat
```

The PC client owns the serial port and exchanges newline-delimited `PB1`
commands and events. `pc_protocol.py` validates framing, sequencing and CRC
before exposing a received payload to the capture and GUI layers.

The firmware keeps serial I/O separate from the radio application. PC uploads
are accepted in 128-byte chunks and are placed in the radio queue only after a
valid length and CRC. `QUEUED` confirms queue acceptance, not over-the-air
delivery.

The GUI worker never touches Qt widgets from the serial thread. It places
validated events into a queue; the Qt main thread updates the chat, users,
status and previews. Received BIN files remain lossless while PNG previews use
the official active drawing polygon.
