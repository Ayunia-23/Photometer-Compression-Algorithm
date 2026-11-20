"""Deterministic correctness tests for the PDC1 reference codec."""

import numpy as np

from codec import HEADER, decode, encode


def main():
    rng = np.random.RandomState(202608)
    cases = {
        "constant": np.full((4096, 4), 32768, dtype=np.uint16),
        "ramp": np.arange(4096 * 4, dtype=np.uint16).reshape(4096, 4),
        "random": rng.randint(0, 65536, (4096, 4), dtype=np.uint16),
        "full_scale_jump": np.tile(
            np.array([[0, 65535, 0, 65535], [65535, 0, 65535, 0]], dtype=np.uint16),
            (2048, 1),
        ),
    }

    for name, source in cases.items():
        packed = encode(source)
        restored = decode(packed)
        assert np.array_equal(source, restored), name
        flags = HEADER.unpack_from(packed)[4]
        print(
            "{:<16} raw={:7d} B  stream={:7d} B  mode={}".format(
                name, source.nbytes, len(packed), "RAW" if flags & 1 else "PDC1"
            )
        )

    damaged = bytearray(encode(cases["constant"]))
    damaged[-5] ^= 1
    try:
        decode(bytes(damaged))
    except ValueError as error:
        assert "CRC-32" in str(error)
    else:
        raise AssertionError("CRC test failed")
    print("round-trip: PASS; CRC corruption detection: PASS")


if __name__ == "__main__":
    main()
