# Public DOGI Parity Audit

- Status: `substantial-direct-evidence-not-full-parity`
- Evidence passed: `5/5`
- Fatal if overclaimed: `true`

The headline same-path DOGI-style baseline is not the public DOGI prototype. The paper therefore keeps exact public DOGI evidence separate: null_blk/ZenFS, six compact physical-ZNS workloads, a dynamic p8000 pressure run, selector variants, and an original-LBA p8000 run all complete. This is substantial direct evidence, but not full end-to-end parity with QUASAR's packed replay.

Paper rule:

> Use same-path baselines for apples-to-apples QUASAR/FIFO/SepBIT/MiDAS/DOGI-style replay. Use exact public DOGI runs only as sanity evidence and never unit-mix their internal GiB counters with packed-ZNS replay WAF or latency.

| Evidence | Passed | WAF | Scope |
| --- | ---: | ---: | --- |
| `nullblk_zenfs_dogi` | `true` | 1.681 | public DOGI prototype on null_blk/ZenFS |
| `six_workload_physical_compact` | `true` | 2.401 | public DOGI prototype on physical ZNS over six DOGI-shaped compact traces |
| `dynamic_pressure_dogi` | `true` | 2.993 | public DOGI prototype on Alibaba-like p8000 compact pressure trace |
| `dynamic_pressure_selector_suite` | `true` | 2.804 | public DOGI prototype DOGI/Greedy/CostBenefit selector variants |
| `original_lba_dynamic_dogi` | `true` | 3.212 | public DOGI prototype on original-LBA Alibaba-like p8000 span |

Remaining parity gaps:

- QUASAR is not implemented inside the public DOGI/ZenFS stack.
- The exact public DOGI counters and QUASAR packed-replay counters use different units and stack boundaries.
- Compact-LBA DOGI runs are feasibility evidence; the original-LBA run exists for one hard dynamic trace only.
- A full production comparison would need the same app/ZenFS/SPDK path for DOGI and QUASAR.
