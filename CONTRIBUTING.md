# Contributing

PictoBridgePC is experimental hardware/protocol software. Contributions are
welcome, but changes should preserve the distinction between:

- USB transport integrity, checked with the serial CRC;
- radio delivery, which is not acknowledged by `QUEUED`;
- image format assumptions, which must not be applied to unknown payloads.

Before opening a pull request:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe -m unittest -v test_pc
.\.venv\Scripts\python.exe -m compileall -q pc_capture.py pc_codec.py pc_protocol.py pictobridge.py pictobridge_gui.py pictobridge_gui_qt.py prepare_sources.py verify_firmware.py test_pc.py
```

Do not commit backups, captures, `.venv`, `vendor/`, private logs, or DSi
conversation data. Firmware changes must identify the target chip and explain
whether the distributed merged image was regenerated.
