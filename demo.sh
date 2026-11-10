#!/usr/bin/env bash
# demo.sh — Start the full AI autoscaling stack in one terminal
set -euo pipefail
export KIND_EXPERIMENTAL_PROVIDER=docker

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

cleanup() {
  echo ""
  echo "[demo] Shutting down port-forwards and autoscaler..."
  kill "$PROM_PID" "$GRAFANA_PID" "$AUTOSCALER_PID" 2>/dev/null || true
  echo "[demo] Done. Run './cluster.sh stop' to pause the cluster."
}
trap cleanup EXIT INT TERM

# 1. Start cluster (wakes existing container or creates fresh one)
echo "[demo] Starting cluster..."
./cluster.sh start

# 2. Port-forward Prometheus and Grafana to localhost (background)
echo "[demo] Starting Prometheus port-forward (localhost:9090)..."
kubectl port-forward svc/prometheus 9090:9090 >/dev/null 2>&1 &
PROM_PID=$!

echo "[demo] Starting Grafana port-forward (localhost:3000)..."
kubectl port-forward svc/grafana 3000:80 >/dev/null 2>&1 &
GRAFANA_PID=$!

sleep 3

# 3. Start the AI predictive autoscaler (background, logs to terminal)
echo "[demo] Starting AI Predictive Autoscaler..."
.venv/bin/python predictive_autoscaler.py --interval 30 --cpod 50 &
AUTOSCALER_PID=$!

echo ""
echo "================================================"
echo "  Everything is running. Open in browser:"
echo "    Grafana:    http://localhost:3000  (admin / admin)"
echo "    Prometheus: http://localhost:9090"
echo "    App:        http://localhost:80/health"
echo ""
echo "  To send traffic (new terminal):"
echo "    python3 traffic.py --rps 150 --duration 60"
echo ""
echo "  Press Ctrl+C to stop everything."
echo "================================================"
echo ""

# Keep alive — wait for autoscaler to exit (or Ctrl+C)
wait $AUTOSCALER_PID
