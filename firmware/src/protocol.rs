pub const IMAGE_BYTES: usize = 10240;
pub const CHUNK_BYTES: usize = 128;

pub fn crc32(data: &[u8]) -> u32 {
    let mut crc = !0u32;
    for b in data {
        crc ^= *b as u32;
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb88320 & 0u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}

pub fn nibble(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

pub fn decode_hex(src: &str, dst: &mut [u8]) -> Result<usize, ()> {
    let raw = src.as_bytes();
    if raw.len() % 2 != 0 || raw.len() / 2 > dst.len() { return Err(()); }
    // Validate before modifying the destination.
    if raw.iter().any(|b| nibble(*b).is_none()) { return Err(()); }
    for (i, pair) in raw.chunks_exact(2).enumerate() {
        dst[i] = nibble(pair[0]).unwrap() * 16 + nibble(pair[1]).unwrap();
    }
    Ok(raw.len() / 2)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn crc_vector() { assert_eq!(crc32(b"123456789"), 0xcbf43926); }
    #[test] fn empty_crc() { assert_eq!(crc32(b""), 0); }
    #[test] fn hex_roundtrip() {
        let mut b = [0; 3];
        assert_eq!(decode_hex("00aAFF", &mut b), Ok(3));
        assert_eq!(b, [0, 170, 255]);
    }
    #[test] fn malformed_hex() {
        let mut b = [9; 3];
        assert!(decode_hex("012", &mut b).is_err());
        assert!(decode_hex("00112233", &mut b).is_err());
        assert!(decode_hex("00GG", &mut b).is_err());
        assert_eq!(b, [9; 3]);
    }
}

