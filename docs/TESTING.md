# Testing and verification

Run the Python test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_pc
```

Compile the project sources:

```powershell
.\.venv\Scripts\python.exe -m py_compile pc_capture.py pc_codec.py pc_protocol.py pictobridge.py pictobridge_gui.py pictobridge_gui_qt.py prepare_sources.py verify_firmware.py test_pc.py
```

Check installed dependencies and the distributed firmware image:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe .\verify_firmware.py
```

The Qt GUI also has an offscreen smoke test for startup, drawing and status
state. Hardware tests still require a real ESP32, a serial connection and a
Nintendo DSi.
