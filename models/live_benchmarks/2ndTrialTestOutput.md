===================================================================
      LIVE KUBERNETES AI AUTOSCALER BENCHMARK SUITE (k6)
===================================================================
  Target URL      : http://localhost:80
  Prometheus URL  : http://localhost:9090
  Traffic Profile : QUICKBURST
  Models to Test  : baseline_static, bilstm, gru, ridge, random_forest
  Pod Capacity    : 50.0 req/s per replica
  Output Directory: models/live_benchmarks
===================================================================


====================================================================
   LIVE IN-CLUSTER BENCHMARK: BASELINE_STATIC
====================================================================
[RESET] Scaling fibserver to 1 replica... Ready (1 replica active).
✓ Running baseline (static 1 replica, no autoscaler).
[WARMUP] Waiting 8s for metrics pipeline synchronization...
[LOAD] Running k6 load test [Profile: QUICKBURST] -> http://10.96.24.217...
    GENERALIZATION BENCHMARK SUMMARY [Profile: QUICKBURST]
    Total Requests Processed : 9690
    Average Latency          : 4.2 ms
    Median Latency (p50)     : 2.0 ms
    P90 Latency              : 9.5 ms
    P95 Latency              : 15.2 ms
    SLA Violation Rate (>1s) : 0.00 %
    HTTP Error Rate          : 0.00 %

====================================================================
   LIVE IN-CLUSTER BENCHMARK: BILSTM
====================================================================
[RESET] Scaling fibserver to 1 replica... Ready (1 replica active).
✓ Autoscaler launched (PID: 69650) with model 'bilstm'.
[WARMUP] Waiting 8s for metrics pipeline synchronization...
[LOAD] Running k6 load test [Profile: QUICKBURST] -> http://10.96.24.217...
    GENERALIZATION BENCHMARK SUMMARY [Profile: QUICKBURST]
    Total Requests Processed : 9685
    Average Latency          : 4.2 ms
    Median Latency (p50)     : 2.1 ms
    P90 Latency              : 8.7 ms
    P95 Latency              : 13.6 ms
    SLA Violation Rate (>1s) : 0.00 %
    HTTP Error Rate          : 0.00 %
✓ Autoscaler process stopped.

====================================================================
   LIVE IN-CLUSTER BENCHMARK: GRU
====================================================================
[RESET] Scaling fibserver to 1 replica... Ready (1 replica active).
✓ Autoscaler launched (PID: 70827) with model 'gru'.
[WARMUP] Waiting 8s for metrics pipeline synchronization...
[LOAD] Running k6 load test [Profile: QUICKBURST] -> http://10.96.24.217...
    GENERALIZATION BENCHMARK SUMMARY [Profile: QUICKBURST]
    Total Requests Processed : 9763
    Average Latency          : 4.0 ms
    Median Latency (p50)     : 2.1 ms
    P90 Latency              : 8.5 ms
    P95 Latency              : 13.4 ms
    SLA Violation Rate (>1s) : 0.00 %
    HTTP Error Rate          : 0.00 %
✓ Autoscaler process stopped.

====================================================================
   LIVE IN-CLUSTER BENCHMARK: RIDGE
====================================================================
[RESET] Scaling fibserver to 1 replica... Ready (1 replica active).
✓ Autoscaler launched (PID: 72553) with model 'ridge'.
[WARMUP] Waiting 8s for metrics pipeline synchronization...
[LOAD] Running k6 load test [Profile: QUICKBURST] -> http://10.96.24.217...
    GENERALIZATION BENCHMARK SUMMARY [Profile: QUICKBURST]
    Total Requests Processed : 10242
    Average Latency          : 2.9 ms
    Median Latency (p50)     : 1.6 ms
    P90 Latency              : 5.6 ms
    P95 Latency              : 9.0 ms
    SLA Violation Rate (>1s) : 0.00 %
    HTTP Error Rate          : 0.00 %
✓ Autoscaler process stopped.

====================================================================
   LIVE IN-CLUSTER BENCHMARK: RANDOM_FOREST
====================================================================
[RESET] Scaling fibserver to 1 replica... Ready (1 replica active).
✓ Autoscaler launched (PID: 74162) with model 'random_forest'.
[WARMUP] Waiting 8s for metrics pipeline synchronization...
[LOAD] Running k6 load test [Profile: QUICKBURST] -> http://10.96.24.217...
    GENERALIZATION BENCHMARK SUMMARY [Profile: QUICKBURST]
    Total Requests Processed : 10116
    Average Latency          : 3.2 ms
    Median Latency (p50)     : 1.7 ms
    P90 Latency              : 6.3 ms
    P95 Latency              : 10.7 ms
    SLA Violation Rate (>1s) : 0.00 %
    HTTP Error Rate          : 0.00 %
✓ Autoscaler process stopped.

✓ Live benchmark results exported:
  CSV : models/live_benchmarks/live_benchmark_leaderboard.csv
  MD  : models/live_benchmarks/live_benchmark_leaderboard.md

[PLOTS] Generating live benchmark comparison figures...
[PLOTS] Generating live benchmark visual comparison charts...
  ✓ Trajectory plot saved: models/live_benchmarks/live_scaling_trajectories.png
  ✓ Summary bars plot saved: models/live_benchmarks/live_sla_latency_comparison.png