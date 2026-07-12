# Real Application Block Trace With PQC Side Writes

This artifact captures a real sysbench fileio workload while a liboqs-based PQC KMS/audit side writer persists lifecycle records.

- Device traced: `/dev/sdc2`
- Mount source: `/dev/sdc2` on `/` (ext4)
- Sysbench mode: `rndrw`
- Sysbench elapsed: `8.026` s
- PQC sessions completed: `64`
- PQC audit records: `192`
- Blkparse event lines: `194570`
- Blkparse write events: `155360`
- Blkparse read events: `14`

## Claim Boundary

This closes the real-application block-trace gap for the current artifact set. It does not close SPDK/ZenFS latency, public DOGI end-to-end parity, physical FDP replay, per-cohort physical erase scope, or device diversity.
