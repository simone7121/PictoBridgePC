# Troubleshooting

## `PermissionError(13)` or an occupied COM port

Only one process can open the ESP32 serial port. Close other PictoBridge GUI
windows, the terminal client, serial monitors and IDE serial consoles. Restart
the GUI and use **Cambia porta** if the device was re-enumerated.

## The GUI opens but the ESP32 is not connected

Use the automatic port dialog, press **Aggiorna**, and confirm the device is a
classic ESP32/WROOM-32. If needed, pass the port explicitly:

```powershell
.\.venv\Scripts\python.exe .\pictobridge_gui.py --port COM3
```

## A DSi does not appear online

Press **Avvia stanza B**, then enter room B on the DSi. Check the diagnostics
panel for `PB1 START_REQUESTED` and `PB1 JOIN`. The firmware image and DSi must
use the supported room/channel configuration.

## A payload is received but its preview is empty

The original payload is still preserved in `ricevuti/`. Only complete payloads
whose lengths align to 1024-byte tile rows are rendered as previews. Unknown
formats are intentionally kept as BIN/JSON rather than being guessed.
