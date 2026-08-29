"""Fetch pinned upstream sources. No flashing, no administrator rights required."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "vendor"
DS_REV = "a98ad5372ff1d44ddb64cfc62231d1eee0aed018"
FOA_REV = "36b47cdc4cf30dd8c10babefc9c64119e834b8ba"


def checkout(url, destination, revision):
    if destination.exists():
        actual = subprocess.check_output(["git", "-C", str(destination), "rev-parse", "HEAD"], text=True).strip()
        if actual != revision:
            raise RuntimeError("Different sources already exist: " + str(destination))
        return
    subprocess.run(["git", "clone", url, str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "checkout", "--detach", revision], check=True)


def main():
    VENDOR.mkdir(exist_ok=True)
    checkout("https://github.com/esp32-open-mac/FoA.git", VENDOR / "FoA", FOA_REV)
    checkout("https://github.com/mjwells2002/foa_dswifi.git", VENDOR / "source-foa-dswifi", DS_REV)
    lib = VENDOR / "foa_dswifi"
    marker = VENDOR / "pictobridge-prepared-v1.txt"
    if lib.exists():
        if marker.exists() and marker.read_text().strip() == DS_REV + " " + FOA_REV:
            print("Pinned sources already prepared.")
            return
        raise RuntimeError("Unrecognised vendor/foa_dswifi exists; preserving it.")
    shutil.copytree(VENDOR / "source-foa-dswifi" / "foa_dswifi", lib)
    manifest = lib / "Cargo.toml"
    content = manifest.read_text()
    old = 'foa = { git = "https://github.com/esp32-open-mac/FoA.git", package = "foa", features = ["esp32"]}'
    if old not in content:
        raise RuntimeError("Unexpected upstream Cargo.toml")
    manifest.write_text(content.replace(old, 'foa = { path = "../FoA/foa", features = ["esp32"]}'))
    app = lib / "src" / "pictochat_application.rs"
    content = app.read_text()
    old = '//thapayload.write_name("host");'
    if old not in content:
        raise RuntimeError("Unexpected upstream identity code")
    replacement = '''for (i, ch) in "PictoPC".encode_utf16().enumerate() {
                        payload.name[i*2..i*2+2].copy_from_slice(&ch.to_le_bytes());
                    }'''
    app.write_text(content.replace(old, replacement))
    marker.write_text(DS_REV + " " + FOA_REV + "\n")
    print("Prepared pinned radio sources. No hardware was accessed.")


if __name__ == "__main__":
    main()
