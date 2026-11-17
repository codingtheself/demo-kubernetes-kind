# Live In-Cluster Kubernetes Benchmark Leaderboard

Evaluated under real traffic using `k6` on Kubernetes Kind with Dang-Quang & Yoo Capacity-Based Dimensioning.

| Rank | Model Architecture | SLA Violations (>1s) | P95 Latency | P50 (Med) | Error Rate | Avg Replicas | Peak Replicas | Pod-Seconds | Reaction Time |
|:----:|:-------------------|:--------------------:|:-----------:|:---------:|:----------:|:------------:|:-------------:|:-----------:|:-------------:|
| 1 | `GRU` | **0.00%** | 9.7 ms | 1.7 ms | 0.00% | 2.1 | 3 | 100 | 0.0s |
| 2 | `RANDOM_FOREST` | **0.00%** | 13.0 ms | 2.2 ms | 0.00% | 2.2 | 3 | 99 | 0.0s |
| 3 | `RIDGE` | **0.00%** | 13.6 ms | 2.0 ms | 0.00% | 2.3 | 4 | 102 | 0.0s |
| 4 | `BILSTM` | **0.00%** | 17.0 ms | 2.3 ms | 0.00% | 1.5 | 3 | 69 | 15.4s |
| 5 | `BASELINE_STATIC` | **0.00%** | 18.2 ms | 2.6 ms | 0.00% | 1.0 | 1 | 46 | N/A |

### Ranking Methodology
1. **SLA Violations Rate (Primary)**: Percentage of HTTP requests exceeding the 1000ms service level objective.
2. **P95 Latency (Secondary)**: 95th percentile latency experienced by real clients during peak traffic bursts.
3. **Error Rate**: Percentage of HTTP 5xx failures or connection timeouts.
4. **Resource Cost**: Total Pod-Seconds consumed over the test lifecycle.
