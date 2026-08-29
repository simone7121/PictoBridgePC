#![no_std]
#![no_main]
#![feature(impl_trait_in_assoc_type)]

extern crate alloc;
mod protocol;

use alloc::vec::Vec;
use core::fmt::Write as FmtWrite;
use embassy_executor::Spawner;
use embassy_futures::select::{select3, Either3};
use embassy_sync::{blocking_mutex::raw::CriticalSectionRawMutex, channel::Channel, signal::Signal};
use embedded_io_async::{Read, Write};
use esp_hal::{clock::CpuClock, timer::timg::TimerGroup, uart::{Config, Uart, UartRx, UartTx}, Async};
use foa::{FoARunner, FoAResources, VirtualInterface};
use foa_dswifi::{DsWiFiSharedResources, runner::DsWiFiRunner,
    pictochat_application::{PictoChatApplication, PictochatInterface, PictochatInterfaceEvent, PictochatSharedData},
    pictochat_packets::MessagePayload};
use heapless::String;
use ieee80211::mac_parser::MACAddress;
use protocol::{crc32, decode_hex, CHUNK_BYTES, IMAGE_BYTES};
use static_cell::StaticCell;
use esp_backtrace as _;

esp_bootloader_esp_idf::esp_app_desc!();

// Upstream defmt output MUST NOT share the USB protocol UART.
#[defmt::global_logger]
struct DiscardLogger;
unsafe impl defmt::Logger for DiscardLogger {
    fn acquire() {}
    unsafe fn release() {}
    unsafe fn write(_: &[u8]) {}
    unsafe fn flush() {}
}
defmt::timestamp!("{=u64}", 0);

#[defmt::panic_handler]
fn defmt_panic() -> ! {
    panic!("Radio stack assertion; capture this backtrace for diagnostics")
}

type Line = String<384>;
const ROOM: u8 = 7;
const CHANNEL: u8 = 7;
const VERSION: &str = "0.1.0";
static COMMANDS: Channel<CriticalSectionRawMutex, Line, 4> = Channel::new();
static EVENTS: Channel<CriticalSectionRawMutex, WireEvent, 2> = Channel::new();
static START: Signal<CriticalSectionRawMutex, ()> = Signal::new();

enum WireEvent {
    Line(Line),
    Image(MessagePayload),
}

fn formatted(args: core::fmt::Arguments<'_>) -> Line {
    let mut s = Line::new();
    let _ = s.write_fmt(args);
    s
}

async fn emit(args: core::fmt::Arguments<'_>) {
    EVENTS.send(WireEvent::Line(formatted(args))).await;
}

#[embassy_executor::task]
async fn radio(mut runner: FoARunner<'static>) { runner.run().await; }

#[embassy_executor::task]
async fn dswifi(mut runner: DsWiFiRunner<'static, 'static>) { runner.run().await; }

#[embassy_executor::task]
async fn pictochat(app: &'static mut PictoChatApplication<'static>) {
    START.wait().await;
    app.run().await;
}

#[embassy_executor::task]
async fn serial_rx(mut rx: UartRx<'static, Async>) {
    let mut line = Line::new();
    let mut dropping = false;
    let mut b = [0u8];
    loop {
        match Read::read(&mut rx, &mut b).await {
            Ok(1) => {
                if b[0] == b'\n' {
                    if !dropping && line.starts_with("PB1 ") {
                        COMMANDS.send(line.clone()).await;
                    }
                    line.clear();
                    dropping = false;
                } else if b[0] != b'\r' {
                    if !b[0].is_ascii() || line.push(b[0] as char).is_err() {
                        dropping = true;
                    }
                }
            }
            _ => { line.clear(); dropping = true; }
        }
    }
}

async fn write_line(tx: &mut UartTx<'static, Async>, line: &str) {
    let _ = tx.write_all(line.as_bytes()).await;
    let _ = tx.write_all(b"\n").await;
}

#[embassy_executor::task]
async fn serial_tx(mut tx: UartTx<'static, Async>) {
    let mut rx_id = 0u32;
    loop {
        match EVENTS.receive().await {
            WireEvent::Line(line) => write_line(&mut tx, &line).await,
            WireEvent::Image(message) => {
                rx_id = rx_id.wrapping_add(1);
                let m = message.from;
                write_line(&mut tx, &formatted(format_args!(
                    "PB1 RX_BEGIN {} {} {:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
                    rx_id, message.message.len(), m[0],m[1],m[2],m[3],m[4],m[5]
                ))).await;
                for (i, chunk) in message.message.chunks(CHUNK_BYTES).enumerate() {
                    let mut line = formatted(format_args!("PB1 RX_DATA {} {} ", rx_id, i * CHUNK_BYTES));
                    for b in chunk { let _ = write!(line, "{:02x}", b); }
                    write_line(&mut tx, &line).await;
                }
                write_line(&mut tx, &formatted(format_args!(
                    "PB1 RX_END {} {:08x}", rx_id, crc32(&message.message)
                ))).await;
            }
        }
    }
}

struct Upload { id: u32, bytes: Vec<u8> }

fn build_info(mac: [u8; 6], started: bool, clients: u8, room: u8, channel: u8) -> Line {
    formatted(format_args!(
        "PB1 INFO pictobridge={} chip=ESP32 room={} channel={} started={} clients={} mac={:02x}{:02x}{:02x}{:02x}{:02x}{:02x} heap={} rx={} tx={}",
        VERSION,
        room,
        channel,
        started as u8,
        clients,
        mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
        esp_alloc::HEAP.free(),
        IMAGE_BYTES,
        IMAGE_BYTES,
    ))
}

fn build_help() -> Line {
    formatted(format_args!(
        "PB1 HELP HELLO STATS INFO START BEGIN DATA COMMIT ABORT"
    ))
}

// Separate task: serial I/O never controls the timing of NiFi acknowledgements.
#[embassy_executor::task]
async fn bridge(interface: PictochatInterface<'static>, mac: [u8; 6]) {
    let mut started = false;
    let mut clients = 0u8;
    let mut upload: Option<Upload> = None;
    loop {
        match select3(interface.inbound_queue.receive(), interface.event_queue.receive(), COMMANDS.receive()).await {
            Either3::First(message) => {
                // Bound USB output / memory use. This is a one-DS experimental bridge.
                if message.message.len() <= IMAGE_BYTES {
                    if EVENTS.try_send(WireEvent::Image(message)).is_err() {
                        // No blocking of the radio stack when the PC is slow.
                        let _ = EVENTS.try_send(WireEvent::Line(formatted(format_args!("PB1 WARN RX_DROPPED"))));
                    }
                } else {
                    emit(format_args!("PB1 WARN RX_SIZE {}", message.message.len())).await;
                }
            }
            Either3::Second(event) => {
                let (kind, id) = match event {
                    PictochatInterfaceEvent::ClientConnected(id) => {
                        clients = clients.saturating_add(1); ("JOIN", id)
                    }
                    PictochatInterfaceEvent::ClientDisconnected(id) => {
                        clients = clients.saturating_sub(1); ("LEAVE", id)
                    }
                };
                let mut line = formatted(format_args!("PB1 {} ", kind));
                for b in id.name { let _ = write!(line, "{:02x}", b); }
                EVENTS.send(WireEvent::Line(line)).await;
            }
            Either3::Third(line) => {
                let mut words = line.split_ascii_whitespace();
                let _ = words.next();
                match words.next() {
                    Some("HELLO") => emit(format_args!(
                        "PB1 READY 1 {:02x}{:02x}{:02x}{:02x}{:02x}{:02x} {} {}",
                        mac[0],mac[1],mac[2],mac[3],mac[4],mac[5], started as u8, clients
                    )).await,
                    Some("STATS") => emit(format_args!("PB1 STATS HEAP_FREE {}", esp_alloc::HEAP.free())).await,
                    Some("INFO") => EVENTS.send(WireEvent::Line(build_info(mac, started, clients, ROOM, CHANNEL))).await,
                    Some("HELP") => EVENTS.send(WireEvent::Line(build_help())).await,
                    Some("START") => {
                        if !started { START.signal(()); started = true; }
                        emit(format_args!("PB1 START_REQUESTED B {}", ROOM)).await;
                    }
                    Some("ABORT") => {
                        upload = None;
                        emit(format_args!("PB1 ABORTED")).await;
                    }
                    Some("BEGIN") => {
                        let id = words.next().and_then(|s| s.parse::<u32>().ok());
                        if !started || clients == 0 {
                            emit(format_args!("PB1 ERROR NO_CLIENT")).await;
                        } else if upload.is_some() {
                            emit(format_args!("PB1 ERROR BUSY")).await;
                        } else if let Some(id) = id {
                            upload = Some(Upload { id, bytes: Vec::with_capacity(IMAGE_BYTES) });
                            emit(format_args!("PB1 OK {} 0", id)).await;
                        } else { emit(format_args!("PB1 ERROR ARGUMENT")).await; }
                    }
                    Some("DATA") => {
                        let id = words.next().and_then(|s| s.parse::<u32>().ok());
                        let offset = words.next().and_then(|s| s.parse::<usize>().ok());
                        let hex = words.next().unwrap_or("");
                        let mut chunk = [0u8; CHUNK_BYTES];
                        let n = decode_hex(hex, &mut chunk);
                        if let (Some(up), Some(id), Some(offset), Ok(n)) = (upload.as_mut(), id, offset, n) {
                            if up.id == id && offset == up.bytes.len() && n > 0 && offset + n <= IMAGE_BYTES {
                                up.bytes.extend_from_slice(&chunk[..n]);
                                emit(format_args!("PB1 OK {} {}", id, up.bytes.len())).await;
                            } else { emit(format_args!("PB1 ERROR OFFSET")).await; }
                        } else { emit(format_args!("PB1 ERROR DATA")).await; }
                    }
                    Some("COMMIT") => {
                        let id = words.next().and_then(|s| s.parse::<u32>().ok());
                        let checksum = words.next().and_then(|s| u32::from_str_radix(s, 16).ok());
                        if let Some(up) = upload.take() {
                            if Some(up.id) != id || up.bytes.len() != IMAGE_BYTES || Some(crc32(&up.bytes)) != checksum {
                                emit(format_args!("PB1 ERROR CHECKSUM_OR_LENGTH")).await;
                            } else if clients == 0 {
                                emit(format_args!("PB1 ERROR NO_CLIENT")).await;
                            } else {
                                let msg = MessagePayload { from: MACAddress::from(mac), message: up.bytes, ..Default::default() };
                                if interface.outbound_queue.try_send(msg).is_ok() {
                                    // QUEUED does NOT mean delivered over the air.
                                    emit(format_args!("PB1 QUEUED {}", up.id)).await;
                                } else { emit(format_args!("PB1 ERROR RADIO_BUSY")).await; }
                            }
                        } else { emit(format_args!("PB1 ERROR NO_UPLOAD")).await; }
                    }
                    _ => emit(format_args!("PB1 ERROR UNKNOWN_COMMAND")).await,
                }
            }
        }
    }
}

#[esp_hal_embassy::main]
async fn main(spawner: Spawner) {
    // 160 MHz is a safer thermal default for continuous radio use on classic ESP32.
    let p = esp_hal::init(esp_hal::Config::default().with_cpu_clock(CpuClock::_160MHz));
    esp_alloc::heap_allocator!(size: 96 * 1024);
    let timg0 = TimerGroup::new(p.TIMG0);
    esp_hal_embassy::init(timg0.timer0);

    let uart = Uart::new(p.UART0, Config::default().with_baudrate(115200)).unwrap()
        .with_tx(p.GPIO1).with_rx(p.GPIO3).into_async();
    let (rx, tx) = uart.split();
    spawner.spawn(serial_rx(rx)).unwrap();
    spawner.spawn(serial_tx(tx)).unwrap();

    static RES: StaticCell<FoAResources> = StaticCell::new();
    let ([vif, ..], runner) = foa::init(RES.init_with(FoAResources::new), p.WIFI, p.ADC2);
    spawner.spawn(radio(runner)).unwrap();
    static VIF: StaticCell<VirtualInterface<'static>> = StaticCell::new();
    static DS: StaticCell<DsWiFiSharedResources<'static>> = StaticCell::new();
    let (control, runner) = foa_dswifi::new_ds_wifi_interface(VIF.init(vif), DS.init_with(DsWiFiSharedResources::default));
    let mac = control.mac_address;
    spawner.spawn(dswifi(runner)).unwrap();
    static SHARED: StaticCell<PictochatSharedData> = StaticCell::new();
    let (app, interface) = PictoChatApplication::new(control, SHARED.init_with(PictochatSharedData::default)).await;
    static APP: StaticCell<PictoChatApplication<'static>> = StaticCell::new();
    spawner.spawn(pictochat(APP.init(app))).unwrap();
    spawner.spawn(bridge(interface, mac)).unwrap();
    emit(format_args!("PB1 BOOT {} ESP32 NO_PSRAM", VERSION)).await;
}
