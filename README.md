# Working_PQC_ZNS

Working repository for a new ZNS storage research direction centered on post-quantum cryptography (PQC) workloads.

## Direction

The current working concept is **QUASAR**: QUantum-safe Append-only Storage ARchitecture for ZNS.

QUASAR targets the mismatch between state-of-the-art ZNS data placement algorithms and PQC workload behavior. Instead of predicting data lifetime from age, access history, or LBA-level features, QUASAR exposes cryptographic intent and epoch metadata from the PQC software stack to the ZNS allocator.

## Core Ideas

- Cryptographic intent-aware zone allocation
- Epoch-based zero-GC reclaim
- Deterministic crypto-erase through zone reset
- Evaluation against FIFO ZNS, SepBIT, MiDAS, and DOGI-style placement

## Repository Layout

- `artifacts/`: generated figures, traces, and experiment artifacts
- `build/`: local build directory
- `code/`: prototype implementation and experiments
- `docs/`: design notes and architecture sketches
- `Paper/`: paper drafts and submission materials
- `HowToWritePaper.md`: working research and writing notes
