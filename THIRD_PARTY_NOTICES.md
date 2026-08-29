# Third-party notices

PictoBridgePC uses or integrates with the following third-party projects and
components. They remain subject to their respective upstream licenses and
notices.

## Firmware SDKs and data

- [FoA](https://github.com/esp32-open-mac/FoA) — BSD-3-Clause.
- [`foa_dswifi`](https://github.com/mjwells2002/foa_dswifi) — see the upstream
  repository for its license and attribution notices.
- ESP32, `esp-hal`, Embassy and related Rust crates — see the package metadata
  and upstream repositories for the applicable licenses.

## PC application dependencies

- [pyserial](https://github.com/pyserial/pyserial) — BSD-3-Clause.
- [Pillow](https://github.com/python-pillow/Pillow) — HPND.
- [PySide6](https://code.qt.io/pyside/pyside-setup) — LGPL-3.0/GPL-2.0/GPL-3.0
  options as described by Qt for the selected distribution.

The exact versions used by the PC application are pinned in
[`requirements.txt`](requirements.txt). Firmware dependency versions are pinned
in [`firmware/Cargo.toml`](firmware/Cargo.toml) and
[`firmware/Cargo.lock`](firmware/Cargo.lock).

This file is an attribution guide, not a replacement for the license text or
notices shipped by each upstream project. See [`LICENSING.md`](LICENSING.md) for
the project's licensing scope and precedence rules.
