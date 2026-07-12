# QUASAR FDP Mapping Model

This is a trace-driven deployment model, not a physical FDP measurement.
It maps QUASAR zone families to a fixed number of FDP placement handles and reports collision/purity pressure.

| Handles | Families | Occupied | Collision Handles | Family Purity | Intent Purity | Avg Families/Handle | Max Families/Handle |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 | 86 | 8 | 8 | 0.8877 | 0.9308 | 10.75 | 18 |
| 16 | 86 | 15 | 15 | 0.8988 | 0.9442 | 5.73 | 11 |
| 32 | 86 | 28 | 26 | 0.9366 | 0.9615 | 3.07 | 6 |
| 64 | 86 | 49 | 27 | 0.9612 | 0.9821 | 1.76 | 4 |
| 128 | 86 | 66 | 17 | 0.9798 | 0.9863 | 1.30 | 3 |

Interpretation:

- High family purity means the FDP handle still mostly represents one QUASAR death cohort.
- Collision handles are expected when the hardware exposes fewer handles than QUASAR families.
- Use this model to decide whether an FDP experiment should use exact epoch families, binned epochs, or tenant/coarse bins.
