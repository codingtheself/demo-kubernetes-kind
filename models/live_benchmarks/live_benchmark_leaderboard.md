# Live In-Cluster Kubernetes Benchmark Leaderboard

Evaluated under real traffic using `k6` on Kubernetes Kind with Dang-Quang & Yoo Capacity-Based Dimensioning.

| Rank | Model Architecture | SLA Violations (>1s) | P95 Latency | P50 (Med) | Error Rate | Avg Replicas | Peak Replicas | Pod-Seconds | Reaction Time |
|:----:|:-------------------|:--------------------:|:-----------:|:---------:|:----------:|:------------:|:-------------:|:-----------:|:-------------:|
| 1 | `RIDGE` | **0.00%** | 9.0 ms | 1.6 ms | 0.00% | 1.8 | 4 | 84 | 11.2s |
| 2 | `RANDOM_FOREST` | **0.00%** | 10.7 ms | 1.6 ms | 0.00% | 1.9 | 4 | 89 | 1.6s |
| 3 | `GRU` | **0.00%** | 13.4 ms | 2.1 ms | 0.00% | 2.1 | 3 | 95 | 0.0s |
| 4 | `BILSTM` | **0.00%** | 13.6 ms | 2.1 ms | 0.00% | 4.0 | 4 | 180 | 0.0s |
| 5 | `BASELINE_STATIC` | **0.00%** | 15.2 ms | 2.0 ms | 0.00% | 1.0 | 1 | 47 | N/A |

### Ranking Methodology
1. **SLA Violations Rate (Primary)**: Percentage of HTTP requests exceeding the 1000ms service level objective.
2. **P95 Latency (Secondary)**: 95th percentile latency experienced by real clients during peak traffic bursts.
3. **Error Rate**: Percentage of HTTP 5xx failures or connection timeouts.
4. **Resource Cost**: Total Pod-Seconds consumed over the test lifecycle.
