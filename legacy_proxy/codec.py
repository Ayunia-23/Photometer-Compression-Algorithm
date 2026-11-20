"""Hardware-oriented lossless codec prototype for interleaved 16-bit ADC data.

The stream is split per channel.  Each channel stores one 16-bit anchor, then
blocks of first differences.  Signed residuals are mapped with ZigZag and each
block stores only the number of bits it actually needs.  This is deliberately
simple to reproduce in FPGA logic; it is a DPTC-style block bit-packer rather
than a general-purpose file compressor.
"""

from __future__ import annotations

import struct
import zlib
from typing import Iterable, Tuple

import numpy as np


MAGIC = b"PDC1"
VERSION = 1
HEADER = struct.Struct("<4sBBBBII")


class BitWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.acc = 0
        self.nbits = 0

    def put(self, value: int, width: int) -> None:
        if width == 0:
            return
        self.acc |= int(value) << self.nbits
        self.nbits += width
        while self.nbits >= 8:
            self.data.append(self.acc & 0xFF)
            self.acc >>= 8
            self.nbits -= 8

    def finish(self) -> bytes:
        if self.nbits:
            self.data.append(self.acc & 0xFF)
        return bytes(self.data)


class BitReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.acc = 0
        self.nbits = 0

    def get(self, width: int) -> int:
        if width == 0:
            return 0
        while self.nbits < width:
            if self.pos >= len(self.data):
                raise ValueError("truncated compressed payload")
            self.acc |= self.data[self.pos] << self.nbits
            self.pos += 1
            self.nbits += 8
        out = self.acc & ((1 << width) - 1)
        self.acc >>= width
        self.nbits -= width
        return out


def _zigzag_encode(delta: int) -> int:
    return (delta << 1) if delta >= 0 else ((-delta << 1) - 1)


def _zigzag_decode(code: int) -> int:
    return (code >> 1) if not (code & 1) else -((code >> 1) + 1)


def encode(samples: np.ndarray, block_size: int = 16) -> bytes:
    """Compress an array shaped ``(sample_count, channel_count)`` losslessly."""
    x = np.asarray(samples)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or x.dtype.kind not in "iu":
        raise TypeError("samples must be a 1-D or 2-D integer array")
    if not 1 <= x.shape[1] <= 255 or not 1 <= block_size <= 255:
        raise ValueError("channel count and block size must be in 1..255")
    if x.size and (x.min() < 0 or x.max() > 65535):
        raise ValueError("input must fit unsigned 16-bit ADC words")

    x = x.astype(np.uint16, copy=False)
    writer = BitWriter()
    for ch in range(x.shape[1]):
        values = x[:, ch]
        if len(values) == 0:
            continue
        writer.put(int(values[0]), 16)
        prev = int(values[0])
        residuals = []
        for value_u16 in values[1:]:
            value = int(value_u16)
            residuals.append(_zigzag_encode(value - prev))
            prev = value
        for start in range(0, len(residuals), block_size):
            block = residuals[start : start + block_size]
            width = max(block, default=0).bit_length()
            writer.put(width, 5)  # residual widths are 0..17 bits
            for code in block:
                writer.put(code, width)

    payload = writer.finish()
    flags = 0
    raw_payload = x.astype("<u2", copy=False).tobytes(order="C")
    if len(payload) >= len(raw_payload):
        payload = raw_payload
        flags = 1  # incompressible-frame escape: send verbatim ADC words
    header = HEADER.pack(
        MAGIC, VERSION, x.shape[1], block_size, flags, x.shape[0], len(payload)
    )
    checksum = struct.pack("<I", zlib.crc32(header + payload) & 0xFFFFFFFF)
    return header + payload + checksum


def decode(stream: bytes) -> np.ndarray:
    """Decode a PDC1 stream and verify its CRC-32."""
    if len(stream) < HEADER.size + 4:
        raise ValueError("stream is shorter than the fixed header")
    magic, version, channels, block_size, flags, count, payload_size = HEADER.unpack_from(stream)
    if magic != MAGIC or version != VERSION or flags not in (0, 1):
        raise ValueError("unsupported stream header")
    expected_size = HEADER.size + payload_size + 4
    if len(stream) != expected_size:
        raise ValueError("stream length does not match header")
    payload = stream[HEADER.size : HEADER.size + payload_size]
    stored_crc = struct.unpack_from("<I", stream, HEADER.size + payload_size)[0]
    if zlib.crc32(stream[: HEADER.size] + payload) & 0xFFFFFFFF != stored_crc:
        raise ValueError("CRC-32 mismatch")

    if flags == 1:
        if payload_size != count * channels * 2:
            raise ValueError("raw payload length does not match dimensions")
        return np.frombuffer(payload, dtype="<u2").reshape(count, channels).copy()

    out = np.empty((count, channels), dtype=np.uint16)
    reader = BitReader(payload)
    for ch in range(channels):
        if count == 0:
            continue
        prev = reader.get(16)
        out[0, ch] = prev
        produced = 1
        while produced < count:
            width = reader.get(5)
            if width > 17:
                raise ValueError("invalid residual width")
            take = min(block_size, count - produced)
            for _ in range(take):
                prev += _zigzag_decode(reader.get(width))
                if not 0 <= prev <= 65535:
                    raise ValueError("decoded sample is outside uint16 range")
                out[produced, ch] = prev
                produced += 1
    return out
