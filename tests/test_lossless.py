import contextlib
import io
from pathlib import Path
import random
import tempfile
import unittest

from lossless_file import compress, decompress, verify


class LosslessTests(unittest.TestCase):
    def test_roundtrip(self):
        rng = random.Random(23)
        datasets = [b'', b'ASIM\x00\xff' * 200000,
                    bytes(rng.getrandbits(8) for _ in range(65536))]
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            for i, data in enumerate(datasets):
                for level in (1, 9):
                    source, packed, restored = [root / ('{}_{}_{}'.format(i, level, n))
                                                 for n in ('input', 'packed', 'restored')]
                    source.write_bytes(data)
                    compress(source, packed, level)
                    decompress(packed, restored)
                    verify(source, restored)
                    self.assertEqual(data, restored.read_bytes())
                    with self.assertRaises(FileExistsError):
                        decompress(packed, restored)

    def test_corruption_and_truncation(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            root = Path(folder)
            source, packed = root / 'input', root / 'packed'
            source.write_bytes(b'photometer data' * 1000)
            compress(source, packed)
            raw = packed.read_bytes()
            corrupted = bytearray(raw)
            corrupted[16] ^= 1  # alter expected SHA-256
            for i, data in enumerate((bytes(corrupted), raw[:-1], raw + b'extra')):
                bad, out = root / ('bad' + str(i)), root / ('out' + str(i))
                bad.write_bytes(data)
                with self.assertRaises(ValueError):
                    decompress(bad, out)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
