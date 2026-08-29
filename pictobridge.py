"""Windows/Linux terminal client. No flashing and no internet connection."""
import argparse
from pathlib import Path
import queue
import threading

import serial
from pc_codec import text_bitmap, test_bitmap
from pc_protocol import Link, ProtocolError
from pc_capture import save_capture


def main():
    parser = argparse.ArgumentParser(description="PictoBridge 0.1 - prototipo sperimentale")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--output", type=Path, default=Path("ricevuti"))
    args = parser.parse_args()
    commands = queue.Queue(maxsize=1)
    stopped = threading.Event()
    ready = threading.Event()

    def log(message):
        if message == "PB1 START_REQUESTED A 7":
            message += " [firmware 0.1: stanza reale B, etichetta A errata]"
        if message.startswith(("PB1 JOIN ", "PB1 LEAVE ")):
            try:
                name = bytes.fromhex(message.split()[2]).decode("utf-16-le", errors="replace").rstrip("\0")
                # Do not allow remote control characters to alter the terminal.
                message += " nome=" + repr(name)
            except (ValueError, IndexError):
                pass
        print("\n" + ascii(message)[1:-1], flush=True)

    def image_received(sender, bitmap):
        raw, png = save_capture(args.output, sender, bitmap)
        log("Payload ricevuto: %d byte. File: %s" % (len(bitmap), raw))
        log("Immagine: " + str(png) if png else "Formato non ancora decodificato; BIN e JSON conservati senza modifiche.")

    def worker():
        port = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=2)
        port.dtr = False
        port.rts = False
        port.port = args.port
        try:
            port.open()
            link = Link(port, log, image_received, stopped.is_set)
            link.handshake()
            ready.set()
            log("USB pronto. Digita start per avviare la stanza, poi entra in B sul DSi.")
            ident = 0
            while not stopped.is_set():
                try:
                    command, data = commands.get_nowait()
                except queue.Empty:
                    link.poll()
                    continue
                try:
                    if command == "start":
                        link.request("START", "PB1 START_REQUESTED")
                    elif command == "status":
                        link.request("HELLO", "PB1 READY")
                        link.request("STATS", "PB1 STATS")
                    elif command == "send":
                        ident += 1
                        link.send_bitmap(data, ident)
                        log("Accodato sull'ESP32; controlla sul DSi se e' arrivato.")
                except (ProtocolError, ValueError) as exc:
                    log(str(exc))
        except (OSError, ProtocolError) as exc:
            log("Connessione interrotta: " + str(exc))
        finally:
            ready.clear()
            stopped.set()
            port.close()

    print("PictoBridge PC 0.1.1 - diagnostica RX, firmware 0.1 stanza B")
    print("Comandi: start | status | info | send Ciao Simone! | pattern | quit")
    print("Le immagini ricevute saranno salvate localmente in:", args.output.resolve())
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        while not stopped.is_set():
            line = input("> ").strip()
            if line == "quit":
                break
            if not ready.is_set():
                print("Attendi USB pronto. Se la connessione e' fallita, esci con quit.")
                continue
            try:
                if line in ("start", "status", "info"):
                    commands.put_nowait((line, None))
                elif line == "pattern":
                    commands.put_nowait(("send", test_bitmap()))
                elif line.startswith("send "):
                    commands.put_nowait(("send", text_bitmap(line[5:])))
                else:
                    print("Comandi: start | status | info | send TESTO | pattern | quit")
            except queue.Full:
                print("Trasferimento occupato; attendi prima di inviare ancora.")
            except ValueError as exc:
                print(exc)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stopped.set()
        thread.join(timeout=3)
        print("Client chiuso. Scollega l'ESP32 dall'USB per spegnere la stanza radio.")


if __name__ == "__main__":
    main()
