# QUASAR-DOGI Space Sensitivity

- Trace: `artifacts/traces/dogi-paper-workloads-smoke/exchange-pqc2000.jsonl`
- Baseline DOGI WAF: 1.011
- Baseline DOGI lifetime utilization: 0.532
- Baseline DOGI stale secrets: 3,748
- Candidate count: 48

## Lowest WAF Settings

| Setting | WAF | GC Blocks | Lifetime Util | Closed Fill | Stale Secrets | Exact Writes | Binned Writes | Retries |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fill=0.00, bin=1, open=1 | 1.001 | 61 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.00, bin=2, open=1 | 1.001 | 61 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.00, bin=1, open=2 | 1.001 | 61 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.00, bin=2, open=2 | 1.001 | 61 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.00, bin=1, open=4 | 1.001 | 61 | 0.515 | 0.961 | 0 | 2,394 | 156 | 0 |
| fill=0.00, bin=2, open=4 | 1.001 | 61 | 0.515 | 0.961 | 0 | 2,394 | 156 | 0 |
| fill=0.00, bin=4, open=4 | 1.001 | 61 | 0.515 | 0.961 | 0 | 2,394 | 156 | 0 |
| fill=0.00, bin=8, open=4 | 1.001 | 61 | 0.515 | 0.961 | 0 | 2,394 | 156 | 0 |

## Highest Utilization Settings

| Setting | WAF | GC Blocks | Lifetime Util | Closed Fill | Stale Secrets | Exact Writes | Binned Writes | Retries |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fill=0.00, bin=4, open=1 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.25, bin=4, open=1 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,315 | 1,235 | 0 |
| fill=0.00, bin=8, open=1 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.25, bin=8, open=1 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,315 | 1,235 | 0 |
| fill=0.00, bin=4, open=2 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.25, bin=4, open=2 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,315 | 1,235 | 0 |
| fill=0.00, bin=8, open=2 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,738 | 812 | 0 |
| fill=0.25, bin=8, open=2 | 1.002 | 76 | 0.515 | 0.961 | 0 | 1,315 | 1,235 | 0 |
