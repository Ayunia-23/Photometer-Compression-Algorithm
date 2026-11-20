# Photometer Compression / 光度计数据无损压缩

提供完整CDF文件的可逆无损压缩、解压、完整性校验和吞吐量评测，并保留面向FPGA的PDC1整数波形候选原型。

## 当前算法与验证范围

正式文件压缩使用 **zlib/DEFLATE（LZ77 + Huffman编码）**，不量化或改变原始字节。
自定义CDFLZ001文件头保存原始长度与SHA-256；解压验证完整性，verify命令直接比较所有字节。
程序支持任意文件，不要求安装CDF解析库。level 1–9均无损，仅影响速度和压缩率。

硬件目标为四路4 MSPS、16位ADC，总输入256 Mbps，期望输出不高于80 Mbps，原网口约束100 Mbps。
当前完成PC文件级验证；实际ADC连续输入、HDL、XC7Z020资源/时序及上板验收尚未完成。
文件压缩比和PC吞吐不能直接代表ADC流式压缩或FPGA性能。

## 快速开始（WSL / Linux）

Python 3.8+，主功能仅需标准库，不需要数据库。

```bash
python3 lossless_file.py compress input.cdf output.cdflz --level 1
python3 lossless_file.py decompress output.cdflz restored.cdf
python3 lossless_file.py verify input.cdf restored.cdf
python3 -m unittest discover -s tests -v
```

输出已存在时程序拒绝覆盖，请使用新路径。SHA-256用于损坏检测，并非数字签名。
临时文件完成后复制发布，不保证原子发布；写入中断后请换新输出路径重试。

## 数据与批量性能测试

本仓库不分发ASIM观测数据、压缩数据副本、第三方论文或开发环境。
数据须由有权限的用户从[ASIM数据中心](https://asdc.space.dtu.dk/)获取并按其使用条件处理，或使用自己的采集文件。

```bash
mkdir -p data
# 将你有权使用的CDF文件放入data目录
python3 benchmark_lossless.py --levels 1 9 --repeat 1 -- data/*.cdf
```

报告与恢复文件保存在results的新子目录；更全面测试可增加等级1/3/6/9和重复次数。
256 Mbps=32 MB/s；输入处理速度至少32 MB/s是PC筛选门槛。
报告的输出Mbps为256除以文件压缩比的折算值，不是网络发送实测，也未包含网络开销。
计时含哈希、I/O和复制发布，OS缓存会影响结果；不做持久落盘极限测试。

## 已有结果

先前对用户提供的4份ASIM Level 1文件完成真实压缩、解压及逐字节/SHA-256比较，全部通过。
level 9的文件大小结果如下；耗时随平台变化，需本机重测。

| 观测号 | 原始字节 | 压缩字节（含头） | 比率 |
|---|---:|---:|---:|
| 1510 | 1,971,370 | 216,663 | 9.099:1 |
| 1528 | 1,940,785 | 240,529 | 8.069:1 |
| 1712 | 7,817,986 | 6,606,093 | 1.183:1 |
| 1730 | 79,161,225 | 67,342,060 | 1.176:1 |

相机类文件不满足3.2:1压缩比目标；level 9速度也不能一概认为满足实时门槛。
原始数据没有包含在仓库中，这些是历史文件级结果，而非本次合成数据CI测试结果。

## 可选PDC1候选

[legacy_proxy](legacy_proxy/)保留一阶差分、ZigZag、16点自适应位宽、RAW回退与CRC实现。
编码器对uint16输入可逆；其benchmark将浮点通量转为整数等级，预处理不可逆，不能用于原始CDF无损结论。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r legacy_proxy/requirements.txt
python legacy_proxy/selftest.py
python legacy_proxy/benchmark.py --csv results/proxy.csv -- data/*.cdf
```

使用最后一条命令前请先创建results目录。主功能无需这些第三方依赖。
研究参考：[DPTC论文](https://arxiv.org/abs/1903.10984)（外部资源，未随包分发）。

代码尚未指定开源许可证；公开可见不等于授予任意使用、修改或再分发许可。
