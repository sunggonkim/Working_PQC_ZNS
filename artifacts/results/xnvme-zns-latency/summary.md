# xNVMe ZNS Latency Probe

| Field | Value |
| --- | --- |
| backend | `xnvme-linux-nvme-sync` |
| device | `/dev/nvme0n1` |
| zone_index | `3` |
| zslba | `1572864` |
| append_count | `4096` |
| lba_nbytes | `4096` |
| append_avg_ns | `21487.328` |
| append_p50_ns | `21843` |
| append_p95_ns | `23124` |
| append_p99_ns | `26064` |
| append_max_ns | `174261` |
| reset_before_ns | `27612` |
| reset_after_ns | `4469600` |
| throughput_mib_s | `181.793` |
| mounted_after | `True` |
| nonempty_after_lines | `0` |

This is a raw xNVMe/Linux NVMe ioctl ZNS command-path probe. It bypasses zonefs and measures one-process Zone Append latency, but it is not an SPDK poll-mode result because the local build lacks a new enough liburing/SPDK backend.
