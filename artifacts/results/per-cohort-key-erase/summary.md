# Per-Cohort Key-Isolated Crypto Erase

This artifact demonstrates a cohort-scoped erase path that does not call shared-namespace NVMe sanitize.

- Cohorts: `8`
- Records: `256`
- Target destroyed cohort: `epoch-4`
- Store bytes: `1479506`
- Before destroy decrypt OK: `256`
- After destroy decrypt OK: `224`
- After destroy missing-key records: `32`
- Wrong-key rejection: `32/32`
- Unrelated cohorts preserved: `True`

## Claim Boundary

This is a cohort-scoped crypto-erase deployment path, not proof that zone reset physically erases NAND. It closes the erase blast-radius issue by moving the destructive primitive from device-wide sanitize to per-cohort encryption-key destruction; chip-off physical remanence still depends on the secrecy and destruction of the cohort DEK.
