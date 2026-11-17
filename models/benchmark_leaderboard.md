# Predictive Autoscaling AI Models — Benchmark Leaderboard

*Evaluated on Alibaba Cloud Microservices Workload Trace*

| Rank | Model Name | MAE (RPS) | RMSE (RPS) | MAPE (%) | Latency (ms) | Parameters | Training Time (s) | Artifact File |
|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| 1 | **Bi-LSTM ◄** | 5.58 | 9.83 | 8.12% | 1.07 | 137,793 | 208.49s | `bilstm_workload_model.pt` |
| 2 | **Random Forest** | 5.50 | 9.72 | 8.14% | 12.51 | 21,612 | 3.94s | `random_forest_workload_model.pkl` |
| 3 | **Ridge Regression** | 5.55 | 9.80 | 8.14% | 0.09 | 13 | 0.01s | `ridge_workload_model.pkl` |
| 4 | **Standard LSTM** | 5.59 | 9.81 | 8.24% | 0.69 | 52,545 | 93.78s | `lstm_workload_model.pt` |
| 5 | **GRU** | 5.60 | 9.76 | 8.39% | 0.85 | 39,937 | 114.88s | `gru_workload_model.pt` |
| 6 | **MLP** | 5.62 | 9.72 | 8.46% | 0.12 | 2,945 | 8.60s | `mlp_workload_model.pt` |
| 7 | **Transformer** | 5.61 | 9.74 | 8.50% | 0.56 | 9,697 | 27.97s | `transformer_workload_model.pt` |
