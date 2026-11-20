"""Benchmark the PDC1 prototype on ASIM photometer proxy data or raw uint16."""

from __future__ import annotations

import argparse
import csv
import sys
import time
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).with_name(".deps")))
from cdflib import CDF  # noqa: E402

from codec import decode, encode


PHOT_VARS = ["PHOT1_photon_flux", "PHOT2_photon_flux", "PHOT3_photon_flux"]


def calibrated_flux_to_proxy_counts(values: np.ndarray) -> np.ndarray:
    """Map monotonic calibrated levels to integer ranks; fill values become 0."""
    a = np.asarray(values, dtype=np.float64).reshape(-1)
    valid = np.isfinite(a) & (a >= 0) & (a < 2**31 - 1)
    levels = np.unique(a[valid])
    out = np.zeros(a.size, dtype=np.uint16)
    out[valid] = np.searchsorted(levels, a[valid]).astype(np.uint16)
    return out


def load_asim(path: Path) -> np.ndarray | None:
    cdf = CDF(path)
    channels = []
    for name in PHOT_VARS:
        info = cdf.varinq(name)
        if info.Data_Type_Description != "CDF_DOUBLE":
            return None
        channels.append(calibrated_flux_to_proxy_counts(cdf.varget(name)))
    n = min(map(len, channels))
    return np.column_stack([x[:n] for x in channels])


def run_one(path: Path, block_size: int) -> dict | None:
    samples = load_asim(path)
    if samples is None:
        return None
    raw = samples.astype("<u2", copy=False).tobytes()
    start = time.perf_counter()
    packed = encode(samples, block_size)
    enc_s = time.perf_counter() - start
    start = time.perf_counter()
    restored = decode(packed)
    dec_s = time.perf_counter() - start
    if not np.array_equal(samples, restored):
        raise AssertionError("lossless round-trip failed")
    z = zlib.compress(raw, 6)
    sample_count = samples.size
    return {
        "file": path.name,
        "samples_per_channel": samples.shape[0],
        "channels": samples.shape[1],
        "raw_bytes": len(raw),
        "pdc1_bytes": len(packed),
        "pdc1_bits_per_sample": 8 * len(packed) / sample_count,
        "pdc1_ratio": len(raw) / len(packed),
        "pdc1_estimated_mbps_at_256_input": 256 * len(packed) / len(raw),
        "encode_ms": enc_s * 1000,
        "decode_ms": dec_s * 1000,
        "zlib_bytes": len(z),
        "zlib_ratio": len(raw) / len(z),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--block", type=int, default=16)
    parser.add_argument("--csv", type=Path, default=Path("benchmark_results.csv"))
    args = parser.parse_args()
    paths = args.paths or sorted(Path(".").glob("*.cdf"))
    rows = []
    for path in paths:
        row = run_one(path, args.block)
        if row is not None:
            rows.append(row)
    if not rows:
        raise SystemExit("No CDF files containing numeric PHOT1/2/3 data were found")
    with args.csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(
            f"{row['file']}: PDC1 {row['pdc1_ratio']:.3f}:1, "
            f"{row['pdc1_bits_per_sample']:.3f} bit/sample, "
            f"estimated {row['pdc1_estimated_mbps_at_256_input']:.1f} Mbps; "
            f"zlib {row['zlib_ratio']:.3f}:1"
        )


if __name__ == "__main__":
    main()
