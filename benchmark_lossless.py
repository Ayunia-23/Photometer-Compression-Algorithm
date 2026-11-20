"""Measure complete-file, lossless compression; no third-party dependencies."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import platform
import tempfile
import time
import zlib

from lossless_file import compress, decompress, digest, verify


def timed(function, *args):
    wall = time.perf_counter()
    cpu = time.process_time()
    with contextlib.redirect_stdout(io.StringIO()):
        function(*args)
    return time.perf_counter() - wall, time.process_time() - cpu


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='*', type=Path)
    parser.add_argument('--levels', nargs='+', type=int, choices=range(1, 10),
                        default=[1, 3, 6, 9])
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--output-root', type=Path, default=Path('results'))
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error('--repeat must be positive')
    files = args.files or sorted(Path('.').glob('*.cdf'))
    if not files or any(not path.is_file() for path in files):
        parser.error('Provide existing input files')
    args.output_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='lossless_bench_', dir=str(args.output_root)))
    rows = []
    print('Output:', output.resolve(), flush=True)
    print('Units: decimal MB/s; target input=32 MB/s=256 Mbps.', flush=True)
    for index, source in enumerate(files):
        for level in args.levels:
            for repeat in range(args.repeat):
                folder = output / ('file{:03d}_level{}_run{}'.format(index, level, repeat + 1))
                folder.mkdir()
                packed = folder / (source.name + '.cdflz')
                restored = folder / source.name
                enc_wall, enc_cpu = timed(compress, source, packed, level)
                dec_wall, dec_cpu = timed(decompress, packed, restored)
                verify_wall, _ = timed(verify, source, restored)
                size, sha = digest(source)
                restored_size, restored_sha = digest(restored)
                if size != restored_size or sha != restored_sha:
                    raise ValueError('Integrity validation failed')
                packed_size = packed.stat().st_size
                enc_mbps = size * 8 / enc_wall / 1e6
                dec_mbps = size * 8 / dec_wall / 1e6
                equivalent_output = 256 * packed_size / size if size else None
                row = dict(file=str(source.resolve()), level=level, run=repeat + 1,
                           original_bytes=size, compressed_bytes=packed_size,
                           restored_bytes=restored_size, ratio=size / packed_size,
                           encode_seconds=enc_wall, decode_seconds=dec_wall,
                           verify_seconds=verify_wall, encode_cpu_seconds=enc_cpu,
                           decode_cpu_seconds=dec_cpu, encode_MBps=enc_mbps / 8,
                           decode_MBps=dec_mbps / 8, encode_Mbps=enc_mbps,
                           decode_Mbps=dec_mbps,
                           file_ratio_equivalent_output_Mbps=equivalent_output,
                           desktop_encode_ge_256_Mbps=enc_mbps >= 256,
                           desktop_decode_ge_256_Mbps=dec_mbps >= 256,
                           file_ratio_equivalent_le_80_Mbps=(equivalent_output is not None
                                                           and equivalent_output <= 80),
                           sha256=sha.hex(), restored_sha256=restored_sha.hex(),
                           byte_comparison='PASS', compressed_path=str(packed.resolve()),
                           restored_path=str(restored.resolve()))
                rows.append(row)
                print('{} level={} run={}  {:.3f}:1  encode={:.2f} MB/s  '
                      'decode={:.2f} MB/s  file-ratio equivalent={:.2f} Mbps  '
                      'byte comparison=PASS'.format(source.name, level, repeat + 1,
                          row['ratio'], row['encode_MBps'], row['decode_MBps'],
                          equivalent_output if equivalent_output is not None else 0), flush=True)
    report = dict(platform=platform.platform(), python=platform.python_version(),
                  zlib=zlib.ZLIB_RUNTIME_VERSION, input_target_Mbps=256,
                  output_budget_Mbps=80, rows=rows,
                  scope='Complete CDF file bytes; not ADC or FPGA streaming acceptance. '
                        'Wall time includes hashes, file I/O and publishing. '
                        'No network transmission measured; repeated runs may use OS cache.')
    (output / 'performance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                            encoding='utf-8')
    lines = ['# 完整CDF无损压缩与吞吐量实测', '', report['scope'], '',
             '| 文件 | 等级 | 次数 | 压缩比 | 压缩MB/s | 解压MB/s | 文件比例折算Mbps | 字节校验 |',
             '|---|---:|---:|---:|---:|---:|---:|---|']
    for row in rows:
        lines.append('| {} | {} | {} | {:.3f} | {:.2f} | {:.2f} | {} | PASS |'.format(
            Path(row['file']).name, row['level'], row['run'], row['ratio'],
            row['encode_MBps'], row['decode_MBps'],
            '{:.2f}'.format(row['file_ratio_equivalent_output_Mbps'])
            if row['file_ratio_equivalent_output_Mbps'] is not None else 'N/A'))
    lines += ['', '参考门槛：编码/解码至少32 MB/s，按文件比例折算不高于80 Mbps。',
              '这些门槛只用于本机文件基线筛选，不能判定目标ADC板卡实时达标。',
              '所有压缩文件和恢复文件均保留；详细哈希、CPU耗时与路径见performance.json。']
    (output / 'performance.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Report:', (output / 'performance.md').resolve(), flush=True)


if __name__ == '__main__':
    main()
