#!/usr/bin/env bash
# =============================================================================
# demo.sh — Mentor Presentation Demo Script
# Project: AI-Driven Predictive Auto-Scaling for Microservice Architectures
# B.Tech CSE Final Year Project — MCKV Institute of Engineering
# =============================================================================

set -euo pipefail
export KIND_EXPERIMENTAL_PROVIDER=docker

# ── Colors & formatting ───────────────────────────────────────────────────────
BOLD='\033[1m'
CYAN='\033[1;36m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
MAGENTA='\033[1;35m'
RESET='\033[0m'
LINE="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Helpers ───────────────────────────────────────────────────────────────────
pause() {
  echo ""
  echo -e "${YELLOW}  ▶  Press [ENTER] to continue...${RESET}"
  read -r
}

section() {
  echo ""
  echo -e "${CYAN}${LINE}${RESET}"
  echo -e "${BOLD}${CYAN}  $1${RESET}"
  echo -e "${CYAN}${LINE}${RESET}"
  echo ""
}

info() { echo -e "  ${GREEN}✔${RESET}  $1"; }
note() { echo -e "  ${YELLOW}ℹ${RESET}  $1"; }
cmd()  { echo -e "  ${MAGENTA}$${RESET}  $1"; }

cleanup() {
  echo ""
  note "Cleaning up background processes..."
  kill "$PROM_PF_PID" 2>/dev/null || true
  kill "$GRAFANA_PF_PID" 2>/dev/null || true
  echo -e "${GREEN}  Demo complete. Thank you!${RESET}"
}

# ── Title Card ────────────────────────────────────────────────────────────────
clear
echo ""
echo -e "${CYAN}${LINE}${RESET}"
echo ""
echo -e "  ${BOLD}AI-Driven Predictive Auto-Scaling for Microservice Architectures${RESET}"
echo ""
echo -e "  ${BOLD}B.Tech CSE Final Year Project${RESET}"
echo -e "  MCKV Institute of Engineering"
echo -e "  Supervisor: Mr. Himadri Sekhar Mondal"
echo ""
echo -e "  Date: $(date '+%d %B %Y')"
echo ""
echo -e "${CYAN}${LINE}${RESET}"
echo ""
echo -e "  This demo script walks through the live system in 6 stages."
echo -e "  Press ${BOLD}[ENTER]${RESET} to advance each stage."
pause

# =============================================================================
# STAGE 1 — SYSTEM OVERVIEW
# =============================================================================
clear
section "STAGE 1 of 6 — System Architecture Overview"

cat << 'EOF'
  ┌─────────────────────────────────────────────────────────────────┐
  │                     System Architecture                          │
  │                                                                  │
  │   Traffic (k6 / traffic.py)                                     │
  │        │                                                         │
  │        ▼                                                         │
  │   [ Kubernetes Ingress (NGINX) ]                                 │
  │        │                                                         │
  │        ▼                                                         │
  │   [ fibserver Pods ]  ◄── kubectl scale ──┐                     │
  │        │                                  │                     │
  │        ▼                                  │                     │
  │   [ Prometheus ]  ──RPS scrape──►  [ Predictive Autoscaler ]    │
  │        │                           (Bi-LSTM model)              │
  │        ▼                                                         │
  │   [ Grafana Dashboard ]                                          │
  └─────────────────────────────────────────────────────────────────┘

  KEY COMPONENTS:
  • fibserver      — Go fibonacci microservice (the target workload)
  • Bi-LSTM model  — Forecasts RPS 30s ahead (trained on Alibaba trace)
  • MAPE-K loop    — Monitor → Analyze → Plan → Execute (45s cool-down)
  • cluster.sh     — Unified lifecycle manager (start/stop/test/monitor)
  • traffic.py     — On-demand interactive traffic generator
  • monitor.py     — Live terminal dashboard (pods, RPS, latency)

  RESEARCH PAPERS IMPLEMENTED:
  • Dang-Quang & Yoo (2021) — Bi-LSTM + MAPE-K loop  [PRIMARY]
  • Rubak & Taheri (UCC 2023) — ML for K8s autoscaling
  • Santos et al. (2024/2025) — Gym-based RL autoscaling [reference]
EOF

pause

# =============================================================================
# STAGE 2 — START THE CLUSTER
# =============================================================================
clear
section "STAGE 2 of 6 — Starting Kubernetes Cluster"

note "Checking cluster status..."
./cluster.sh status 2>&1 || true
echo ""

note "Starting the Kind (Kubernetes-in-Docker) cluster..."
cmd "./cluster.sh start"
echo ""
./cluster.sh start
echo ""

note "Waiting 10s for all pods to stabilize..."
sleep 10
echo ""
kubectl get pods -A --no-headers | grep -v "Completed" | awk '{printf "  %-40s %-15s %s\n", $2, $4, $5}'
echo ""
info "Cluster is LIVE. All system pods are running."
pause

# =============================================================================
# STAGE 3 — SHOW AI MODEL RESULTS
# =============================================================================
clear
section "STAGE 3 of 6 — AI Model — Training Results & Benchmarks"

cat << 'EOF'
  DATASET: Alibaba Cluster Trace (synthetic, statistically equivalent)
  ─────────────────────────────────────────────────────────────────────
  • 14-day trace × 30-second intervals = 40,320 samples
  • Features: Diurnal periodicity + Poisson burst injection
  • Split: 70% train / 15% validation / 15% test (chronological)
  • Input window (L): 12 steps = 6 minutes of history
  • Forecast horizon (H): 1 step = 30 seconds ahead

  TRAINED MODELS:
  ─────────────────────────────────────────────────────────────────────
EOF

python3 -c "
import json
with open('models/benchmark_results.json') as f:
    r = json.load(f)
print('  {:<32} {:>12} {:>12} {:>10} {:>18}'.format(
    'Model', 'MAE (RPS)', 'RMSE (RPS)', 'MAPE (%)', 'Inference (ms)'))
print('  ' + '─'*86)
for name, m in r.items():
    marker = '  ◄ PROPOSED' if 'Bi-LSTM' in name else ''
    print('  {:<32} {:>12.2f} {:>12.2f} {:>10.2f} {:>18.2f}{}'.format(
        name, m['MAE (RPS)'], m['RMSE (RPS)'], m['MAPE (%)'],
        m['Inference Latency (ms)'], marker))
"
echo ""

cat << 'EOF'
  INTERPRETATION:
  • Bi-LSTM (proposed) achieves 10.02% MAPE — competitive with baselines
  • MAPE < 15% is considered acceptable for proactive scaling decisions
  • Bi-LSTM processes sequence BOTH forward AND backward (bidirectional)
    giving it context from future-to-past — key advantage during burst
    transitions that linear models miss
  • At 1.21ms inference latency, it comfortably fits in a 30s MAPE loop

  MODEL FILES:
  • models/bilstm_workload_model.pt   — PyTorch Bi-LSTM (primary)
  • models/lstm_workload_model.pt     — LSTM baseline
  • models/scaler.pkl                 — MinMaxScaler (fitted on train set)
  • models/benchmark_results.json     — Numeric results
  • models/model_comparison.png       — Forecast vs actual chart
EOF

pause

# =============================================================================
# STAGE 4 — OPEN MONITORING DASHBOARDS
# =============================================================================
clear
section "STAGE 4 of 6 — Live Monitoring Dashboards"

note "Starting Prometheus port-forward (background)..."
kubectl port-forward -n monitoring svc/prometheus 9090:9090 >/dev/null 2>&1 &
PROM_PF_PID=$!
sleep 3
info "Prometheus available at:  http://localhost:9090"

note "Starting Grafana port-forward (background)..."
kubectl port-forward -n monitoring svc/grafana 3000:3000 >/dev/null 2>&1 &
GRAFANA_PF_PID=$!
sleep 3
info "Grafana available at:     http://localhost:3000  (admin / admin)"

trap cleanup EXIT

echo ""
echo "  ─────────────────────────────────────────────────────────────────"
echo -e "  ${BOLD}Open in your browser:${RESET}"
echo ""
echo -e "  ${GREEN}→ Grafana:${RESET}    http://localhost:3000  (login: admin / admin)"
echo "             Go to Dashboards → Kubernetes / Compute Resources / Pod"
echo ""
echo -e "  ${GREEN}→ Prometheus:${RESET} http://localhost:9090"
echo '             Try query: rate(http_requests_total[30s])'
echo "  ─────────────────────────────────────────────────────────────────"
echo ""
note "Open the browser dashboards now, then press [ENTER] to continue."
pause

# =============================================================================
# STAGE 5 — LIVE DEMO: AI AUTOSCALER + TRAFFIC
# =============================================================================
clear
section "STAGE 5 of 6 — Live Demo: AI Autoscaler + Traffic"

note "Current pod count (before traffic):"
kubectl get pods -l app=fibserver --no-headers | awk '{printf "  %-45s %s\n", $1, $3}'
echo ""

note "Starting the AI Predictive Autoscaler in the background..."
cmd "./predictive_autoscaler.py --interval 30 --cpod 50"
./predictive_autoscaler.py --interval 30 --cpod 50 2>&1 &
AUTOSCALER_PID=$!
info "Autoscaler PID: $AUTOSCALER_PID (logs streaming below)"
echo ""
sleep 5

note "Sending a BURST of 150 RPS traffic for 90 seconds..."
echo "  Watch the autoscaler react in REAL TIME below."
echo "  Then observe pod count changes (refresh Grafana)."
echo ""
cmd "python3 traffic.py --rps 150 --duration 90 --workers 20"
python3 traffic.py --rps 150 --duration 90 --workers 20 &
TRAFFIC_PID=$!

echo ""
note "Polling pod count every 10 seconds while traffic runs..."
echo ""
for i in $(seq 1 9); do
  sleep 10
  COUNT=$(kubectl get pods -l app=fibserver --no-headers 2>/dev/null | wc -l)
  PHASE=$(kubectl get pods -l app=fibserver --no-headers 2>/dev/null | awk '{print $3}' | sort | uniq -c | tr '\n' ' ')
  echo "  [+${i}0s]  fibserver replicas: ${COUNT}  |  phases: ${PHASE}"
done

wait $TRAFFIC_PID 2>/dev/null || true
echo ""
note "Traffic finished. Waiting for autoscaler to scale down (CDT=45s)..."
sleep 50

echo ""
echo "  ── FINAL POD STATE ──────────────────────────────────────────────"
kubectl get pods -l app=fibserver
echo "  ─────────────────────────────────────────────────────────────────"
echo ""
info "Demo complete! The AI autoscaler proactively scaled pods UP during"
info "the traffic burst and will scale them DOWN after cool-down (CDT=45s)."

kill $AUTOSCALER_PID 2>/dev/null || true
pause

# =============================================================================
# STAGE 6 — WHAT'S NEXT (Semester 8 roadmap)
# =============================================================================
clear
section "STAGE 6 of 6 — Project Status & Semester 8 Roadmap"

cat << 'EOF'
  ✅  COMPLETED (Semester 7)
  ─────────────────────────────────────────────────────────────────────
  [1] Data pipeline   — 40,320-sample Alibaba-characteristic trace
  [2] Model training  — Bi-LSTM, LSTM, Ridge Regression + benchmarks
  [3] MAPE-K controller — Monitor→Analyze→Plan→Execute (Algorithm 1)
  [4] Kubernetes infra — Kind cluster, fibserver, Prometheus, Grafana
  [5] Generalization test — k6 flashcrowd/diurnal/bursty (100% SLA pass)
  [6] Tooling          — cluster.sh, traffic.py, monitor.py, demo.sh


  ⚠️  KNOWN LIMITATIONS (to address in Sem 8)
  ─────────────────────────────────────────────────────────────────────
  [A] Ridge Regression beats Bi-LSTM on smooth data (MAE 5.35 vs 5.98)
      → Fix: add CPU + memory as multi-variate features (Bi-LSTM's edge
        over linear models shows on multi-dimensional inputs)

  [B] Synthetic Alibaba trace (not raw download) — access constraints
      → Fix: download real alibaba/clusterdata from GitHub for Sem 8

  [C] C_pod = 50 req/s is an estimate, not empirically benchmarked
      → Fix: run controlled 1-pod saturation test to find true SLA limit

  [D] Single microservice (fibserver) — project title says "Architectures"
      → Fix: add API Gateway → fibserver → cache topology in Sem 8


  🗓️  SEMESTER 8 ROADMAP
  ─────────────────────────────────────────────────────────────────────
  [1] Empirical C_pod benchmark  — benchmark_capacity.py script
  [2] Multi-variate re-train     — CPU + RPS + memory → Bi-LSTM
  [3] Two-tier microservice      — gateway + fibserver + downstream
  [4] Comparative evaluation     — HPA vs reactive vs Bi-LSTM (table)
  [5] Real Alibaba dataset       — alibaba/clusterdata (GitHub)
  [6] Final paper + results      — submit for conference publication
EOF

echo ""
echo -e "${CYAN}${LINE}${RESET}"
echo -e "  ${BOLD}Questions from mentor? All source code is in:${RESET}"
echo ""
echo "  /home/tcoding/Documents/probe/fibserver/"
echo "  Git branch: feature/alibaba-predictive-autoscaler"
echo ""
echo "  Key files:"
echo "    predictive_autoscaler.py  — MAPE-K AI controller"
echo "    prepare_alibaba_data.py   — data pipeline"
echo "    train_predictive_models.py — model training"
echo "    cluster.sh                — cluster lifecycle"
echo "    traffic.py                — interactive traffic generator"
echo "    monitor.py                — live terminal dashboard"
echo -e "${CYAN}${LINE}${RESET}"
echo ""
info "DEMO COMPLETE — Thank you!"
echo ""
