# Kubernetes Cluster Simulation & SLA Audit Leaderboard

*Simulated over 6,047 test intervals (~50 hours) on Alibaba Cloud Microservices Workload*

| Policy / Model | SLA Violations (%) | Max Deficit (RPS) | Average Replicas | Capacity Waste (%) | Total Pod-Hours |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Bi-LSTM** | 4.17% | 113.0 RPS | 1.92 | 31.17% | 96.60 |
| GRU | 4.02% | 113.0 RPS | 1.92 | 31.28% | 96.78 |
| Standard LSTM | 4.17% | 113.0 RPS | 1.92 | 31.13% | 96.55 |
| MLP | 4.25% | 113.0 RPS | 1.92 | 31.22% | 96.63 |
| Random Forest | 4.15% | 113.0 RPS | 1.92 | 31.25% | 96.69 |
| Ridge Regression | 4.70% | 113.0 RPS | 1.90 | 30.70% | 95.90 |
| Transformer | 4.63% | 113.0 RPS | 1.90 | 30.74% | 95.96 |
| Static (4 Pods Always) | 0.05% | 13.0 RPS | 4.00 | 66.73% | 201.57 |
| Reactive Baseline (Lags 1 Step) | 6.50% | 113.0 RPS | 1.94 | 32.00% | 97.51 |
