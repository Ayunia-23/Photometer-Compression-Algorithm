"""Reversible, byte-exact file compression. Python 3.8+, standard library only.

This format uses zlib/DEFLATE, not the PDC1 ADC proxy codec.
"""
import argparse
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import zlib

HEADER = struct.Struct('<8sQ32s')
MAGIC = b'CDFLZ001'
CHUNK = 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(CHUNK), b''):
            h.update(data)
            size += len(data)
    return size, h.digest()


def temporary_output(path):
    path = Path(path)
    if path.exists():
        raise FileExistsError('Output already exists: {}'.format(path))
    return tempfile.NamedTemporaryFile(mode='w+b', dir=str(path.parent),
                                       prefix='.lossless-', delete=False)


def publish(temp, destination):
    # Exclusive creation: never overwrite an existing file.
    with open(destination, 'xb') as target, open(temp, 'rb') as source:
        for data in iter(lambda: source.read(CHUNK), b''):
            target.write(data)


def compress(source, destination, level=9):
    if level not in range(1, 10):
        raise ValueError('Compression level must be 1..9')
    source, destination = Path(source), Path(destination)
    size, expected_hash = digest(source)
    temp = temporary_output(destination)
    name = temp.name
    try:
        with temp, source.open('rb') as f:
            temp.write(HEADER.pack(MAGIC, size, expected_hash))
            encoder = zlib.compressobj(level)
            actual_hash = hashlib.sha256()
            actual_size = 0
            for data in iter(lambda: f.read(CHUNK), b''):
                actual_hash.update(data)
                actual_size += len(data)
                temp.write(encoder.compress(data))
            temp.write(encoder.flush())
            if actual_size != size or actual_hash.digest() != expected_hash:
                raise ValueError('Input changed during compression')
        publish(name, destination)
    finally:
        os.unlink(name)
    packed = destination.stat().st_size
    ratio = size / packed if packed else 0
    print('Original: {} bytes; compressed: {} bytes; ratio: {:.3f}:1'.format(
        size, packed, ratio))
    print('SHA-256:', expected_hash.hex())


def decompress(source, destination):
    source, destination = Path(source), Path(destination)
    with source.open('rb') as f:
        header = f.read(HEADER.size)
        if len(header) != HEADER.size:
            raise ValueError('Truncated header')
        magic, expected_size, expected_hash = HEADER.unpack(header)
        if magic != MAGIC:
            raise ValueError('Unsupported file format')
        temp = temporary_output(destination)
        name = temp.name
        try:
            with temp:
                decoder = zlib.decompressobj()
                h = hashlib.sha256()
                size = 0
                for data in iter(lambda: f.read(CHUNK), b''):
                    if decoder.eof:
                        raise ValueError('Unexpected trailing data')
                    pending = data
                    while pending:
                        restored = decoder.decompress(pending, CHUNK)
                        pending = decoder.unconsumed_tail
                        size += len(restored)
                        if size > expected_size:
                            raise ValueError('Decoded size exceeds header')
                        h.update(restored)
                        temp.write(restored)
                        if decoder.unused_data:
                            raise ValueError('Unexpected trailing data')
                if not decoder.eof:
                    raise ValueError('Truncated compressed payload')
                if size != expected_size or h.digest() != expected_hash:
                    raise ValueError('Size or SHA-256 validation failed')
            publish(name, destination)
        finally:
            os.unlink(name)
    print('Restored: {} bytes; integrity: PASS'.format(size))
    print('SHA-256:', expected_hash.hex())


def verify(first, second):
    # Compare bytes directly, not only hashes.
    with Path(first).open('rb') as a, Path(second).open('rb') as b:
        while True:
            x, y = a.read(CHUNK), b.read(CHUNK)
            if x != y:
                raise ValueError('Files differ')
            if not x:
                break
    print('Byte-for-byte comparison: PASS')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['compress', 'decompress', 'verify'])
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--level', type=int, choices=range(1, 10), default=9,
                   help='Compression effort, 1 fastest to 9 highest; all lossless')
    args = p.parse_args()
    try:
        if args.operation == 'compress':
            compress(args.input, args.output, args.level)
        else:
            {'decompress': decompress, 'verify': verify}[args.operation](args.input, args.output)
    except (OSError, ValueError, zlib.error) as error:
        p.exit(1, 'ERROR: {}\n'.format(error))


if __name__ == '__main__':
    main()
