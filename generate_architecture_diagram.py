#!/usr/bin/env python3
"""
generate_architecture_diagram.py - Publication-Grade Architecture Diagram Generator
Produces an ultra-high-resolution, perfectly aligned system architecture diagram
for the B.Tech Final Year Project Report & Thesis.
"""

import os
import sys

# Auto re-exec into local virtualenv
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, ArrowStyle


def draw_card(ax, x, y, w, h, bg_color="#FFFFFF", border_color="#CBD5E1", border_width=1.5, radius=0.012, zorder=2, shadow=True):
    """Draw a card with rounded corners and a soft drop shadow."""
    if shadow:
        shadow_patch = FancyBboxPatch(
            (x + 0.0025, y - 0.0035), w, h,
            boxstyle=f"round,pad=0,rounding_size={radius}",
            facecolor="#0F172A", alpha=0.06,
            edgecolor="none", zorder=zorder - 1
        )
        ax.add_patch(shadow_patch)

    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        facecolor=bg_color,
        edgecolor=border_color,
        linewidth=border_width,
        zorder=zorder
    )
    ax.add_patch(patch)
    return patch


def draw_arrow(ax, start, end, color="#2563EB", width=2.0, rad=0.0, zorder=5, label="", label_pos=0.5, label_bg="#FFFFFF", label_color=None):
    """Draw an arrow with an optional high-contrast text badge."""
    connectionstyle = f"arc3,rad={rad}" if rad != 0.0 else "arc3,rad=0"
    arrow = patches.FancyArrowPatch(
        start, end,
        connectionstyle=connectionstyle,
        arrowstyle=ArrowStyle("Simple, tail_width=1.1, head_width=5.5, head_length=6.5"),
        color=color,
        linewidth=width,
        zorder=zorder
    )
    ax.add_patch(arrow)

    if label:
        lx = start[0] + (end[0] - start[0]) * label_pos
        ly = start[1] + (end[1] - start[1]) * label_pos
        txt_col = label_color or color
        ax.text(
            lx, ly, label,
            fontsize=8, fontweight="bold", color=txt_col,
            ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.22", facecolor=label_bg, edgecolor=color, alpha=0.96, linewidth=1.1),
            zorder=zorder + 1
        )


def main():
    fig = plt.figure(figsize=(19, 11.5), dpi=300)
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Global canvas background
    canvas_bg = FancyBboxPatch((0, 0), 1, 1, boxstyle="square,pad=0", facecolor="#F8FAFC", edgecolor="none", zorder=0)
    ax.add_patch(canvas_bg)

    # =========================================================================
    # 0. HEADER BLOCK
    # =========================================================================
    draw_card(ax, 0.02, 0.915, 0.96, 0.072, bg_color="#0F172A", border_color="#1E293B", border_width=2.0, radius=0.010, shadow=True)
    ax.text(0.50, 0.962, "AI-DRIVEN PREDICTIVE AUTOSCALER FOR KUBERNETES MICROSERVICES",
            fontsize=17.5, fontweight="bold", color="#F8FAFC", ha="center", va="center")
    ax.text(0.50, 0.932, "End-to-End System Architecture: Production Alibaba Traces • MAPE-K Control Loop • Deep Learning Forecaster Zoo • Live In-Cluster Feedback",
            fontsize=10.5, color="#94A3B8", ha="center", va="center")

    # =========================================================================
    # 1. ZONE 1: WORKLOAD & TRAFFIC GENERATION (LEFT)
    # =========================================================================
    draw_card(ax, 0.02, 0.04, 0.21, 0.855, bg_color="#F1F5F9", border_color="#CBD5E1", border_width=1.6, radius=0.012)
    
    # Header Badge
    draw_card(ax, 0.03, 0.845, 0.19, 0.038, bg_color="#1E293B", border_color="#334155", radius=0.007, shadow=False)
    ax.text(0.125, 0.864, "1. WORKLOAD GENERATION", fontsize=10.5, fontweight="bold", color="#F8FAFC", ha="center", va="center")

    # 1A: Alibaba Cloud Production Dataset
    draw_card(ax, 0.032, 0.655, 0.186, 0.175, bg_color="#FFFFFF", border_color="#94A3B8", radius=0.009)
    ax.text(0.042, 0.805, "Alibaba Production Traces", fontsize=10, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.042, 0.783, "• Dataset: MCRRTUpdate_0", fontsize=8.2, color="#334155", va="center")
    ax.text(0.042, 0.763, "• Scale: 14.8M Production RPCs", fontsize=8.2, color="#334155", va="center")
    ax.text(0.042, 0.743, "• Microservice Call Latencies & Rates", fontsize=8.2, color="#334155", va="center")
    ax.text(0.042, 0.723, "• Empirical Burstiness Factor: 15.0x", fontsize=8.2, color="#B91C1C", fontweight="bold", va="center")
    ax.text(0.042, 0.697, "Preprocessing: 10s Window Aggregation", fontsize=8, color="#2563EB", fontweight="bold", va="center")
    ax.text(0.042, 0.677, "Train (70%) / Val (15%) / Test (15%)", fontsize=7.8, color="#64748B", va="center")

    # 1B: k6 Generalization Engine
    draw_card(ax, 0.032, 0.385, 0.186, 0.255, bg_color="#FFFFFF", border_color="#94A3B8", radius=0.009)
    ax.text(0.042, 0.615, "k6 Synthetic Load Generator", fontsize=10, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.042, 0.595, "Container: grafana/k6:0.53.0", fontsize=8.2, color="#475569", va="center")

    draw_card(ax, 0.040, 0.400, 0.170, 0.180, bg_color="#F8FAFC", border_color="#E2E8F0", radius=0.007, shadow=False)
    ax.text(0.046, 0.560, "Dynamic Load Profiles:", fontsize=8.5, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.046, 0.538, "1. Quickburst (55s Stepped Surge to 280 RPS)", fontsize=7.8, color="#4338CA", fontweight="bold", va="center")
    ax.text(0.046, 0.518, "2. Flash Crowd (Sudden 10s Surge)", fontsize=7.8, color="#B91C1C", va="center")
    ax.text(0.046, 0.498, "3. Diurnal Wave (Smooth Multi-Phase)", fontsize=7.8, color="#0369A1", va="center")
    ax.text(0.046, 0.478, "4. Stochastic Bursty (Anti-Thrash Test)", fontsize=7.8, color="#B45309", va="center")
    ax.text(0.046, 0.448, "Measured Metrics: Requests, Throughput,", fontsize=7.5, color="#334155", va="center")
    ax.text(0.046, 0.428, "P50, P90, P95 Tail Latency, SLA (>1s) %", fontsize=7.5, color="#15803D", fontweight="bold", va="center")

    # 1C: Interactive Traffic Generator
    draw_card(ax, 0.032, 0.145, 0.186, 0.225, bg_color="#FFFFFF", border_color="#94A3B8", radius=0.009)
    ax.text(0.042, 0.345, "Interactive Traffic CLI", fontsize=10, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.042, 0.325, "Script: traffic.py / cluster.sh traffic", fontsize=8.2, color="#475569", va="center")
    ax.text(0.042, 0.298, "• Multi-threaded worker pool (16 VUs)", fontsize=8.2, color="#334155", va="center")
    ax.text(0.042, 0.278, "• Manual RPS step modulation slider", fontsize=8.2, color="#334155", va="center")
    ax.text(0.042, 0.258, "• Random Fibonacci seed n ∈ [15 .. 20]", fontsize=8.2, color="#334155", va="center")
    ax.text(0.042, 0.238, "• Client-side latency & error calculation", fontsize=8.2, color="#334155", va="center")
    ax.text(0.042, 0.200, "Targets Ingress / Service IP:", fontsize=8, fontweight="bold", color="#2563EB", va="center")
    ax.text(0.042, 0.180, "http://localhost:80/fib/:n", fontsize=7.8, color="#0F172A", va="center")
    ax.text(0.042, 0.160, "http://10.96.24.217:80 (ClusterIP)", fontsize=7.8, color="#64748B", va="center")

    # =========================================================================
    # 2. ZONE 2: KUBERNETES TARGET CLUSTER (CENTER)
    # =========================================================================
    draw_card(ax, 0.245, 0.385, 0.405, 0.510, bg_color="#EFF6FF", border_color="#BFDBFE", border_width=1.6, radius=0.012)
    
    # Header Badge
    draw_card(ax, 0.255, 0.845, 0.385, 0.038, bg_color="#1D4ED8", border_color="#1E40AF", radius=0.007, shadow=False)
    ax.text(0.4475, 0.864, "2. KUBERNETES TARGET CLUSTER (KIND INFRASTRUCTURE)", fontsize=10.5, fontweight="bold", color="#FFFFFF", ha="center", va="center")

    # 2A: Kubernetes Control Plane (kube-apiserver)
    draw_card(ax, 0.260, 0.725, 0.375, 0.105, bg_color="#FFFFFF", border_color="#93C5FD", radius=0.009)
    ax.text(0.270, 0.805, "Kubernetes Control Plane (API Server & Controller)", fontsize=10, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.270, 0.785, "Endpoint: https://10.89.0.2:6443 | Kind Node Daemon", fontsize=8, color="#64748B", va="center")
    ax.text(0.270, 0.760, "• Handles Scale Subresource: PATCH /apis/apps/v1/.../deployments/fibserver/scale", fontsize=8, color="#1E293B", va="center")
    ax.text(0.270, 0.740, "• Kube-Controller-Manager reconciles desired replicas spec.replicas with Kubelet", fontsize=8, color="#2563EB", fontweight="bold", va="center")

    # 2B: Ingress & Service Routing (Separated by a 0.055 corridor at x=0.420 to 0.475)
    draw_card(ax, 0.260, 0.585, 0.160, 0.125, bg_color="#FFFFFF", border_color="#93C5FD", radius=0.009)
    ax.text(0.270, 0.685, "NGINX Ingress", fontsize=9.5, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.270, 0.665, "ingress-nginx-controller", fontsize=7.5, color="#64748B", va="center")
    ax.text(0.270, 0.640, "• Host Port 80/443 Binding", fontsize=7.8, color="#334155", va="center")
    ax.text(0.270, 0.620, "• Path routing: /fib/:n", fontsize=7.8, color="#334155", va="center")
    ax.text(0.270, 0.600, "• Reverse proxy & pool", fontsize=7.8, color="#334155", va="center")

    draw_card(ax, 0.475, 0.585, 0.160, 0.125, bg_color="#FFFFFF", border_color="#93C5FD", radius=0.009)
    ax.text(0.485, 0.685, "Kube-Proxy & Service", fontsize=9.5, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.485, 0.665, "Service: fibserver (ClusterIP)", fontsize=7.5, color="#64748B", va="center")
    ax.text(0.485, 0.640, "• IP: 10.96.24.217:80", fontsize=7.8, color="#334155", va="center")
    ax.text(0.485, 0.620, "• IPVS / iptables Balancing", fontsize=7.8, color="#334155", va="center")
    ax.text(0.485, 0.600, "• Endpoint Pod Tracking", fontsize=7.8, color="#334155", va="center")

    # 2C: Microservice Deployment (fibserver)
    draw_card(ax, 0.260, 0.398, 0.375, 0.175, bg_color="#FFFFFF", border_color="#93C5FD", radius=0.009)
    ax.text(0.270, 0.550, "Microservice Deployment: fibserver (Default Namespace)", fontsize=10, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.270, 0.530, "Config: C_pod = 50 req/s | Bounds: [R_min = 1 .. R_max = 8 Replicas]", fontsize=8.2, color="#2563EB", fontweight="bold", va="center")

    # Pod Blocks (4 visualized)
    pod_colors = ["#10B981", "#10B981", "#3B82F6", "#94A3B8"]
    pod_titles = ["Pod-1 (Active)", "Pod-2 (Scaled)", "Pod-3 (Scaled)", "Pod-N (Pool)"]
    pod_subtitles = ["10.244.0.3", "10.244.0.4", "10.244.0.5", "Up to 8 Pods"]
    for i in range(4):
        px = 0.270 + i * 0.089
        draw_card(ax, px, 0.408, 0.082, 0.110, bg_color="#F8FAFC", border_color=pod_colors[i], border_width=1.5, radius=0.006, shadow=False)
        ax.text(px + 0.041, 0.495, pod_titles[i], fontsize=7.5, fontweight="bold", color=pod_colors[i], ha="center", va="center")
        ax.text(px + 0.041, 0.473, pod_subtitles[i], fontsize=7, color="#1E293B", ha="center", va="center")
        ax.text(px + 0.041, 0.450, "fibserver:latest", fontsize=6.8, color="#475569", ha="center", va="center")
        ax.text(px + 0.041, 0.425, "Port 3000 | /metrics", fontsize=6.5, color="#64748B", ha="center", va="center")

    # =========================================================================
    # 3. ZONE 3: OBSERVABILITY & TELEMETRY LAYER (BOTTOM-CENTER)
    # =========================================================================
    draw_card(ax, 0.245, 0.04, 0.405, 0.330, bg_color="#F0FDF4", border_color="#BBF7D0", border_width=1.6, radius=0.012)
    
    # Header Badge (Positioned over Grafana column to leave Prometheus top completely open)
    draw_card(ax, 0.255, 0.320, 0.125, 0.038, bg_color="#15803D", border_color="#166534", radius=0.007, shadow=False)
    ax.text(0.3175, 0.339, "3. TELEMETRY", fontsize=9.5, fontweight="bold", color="#FFFFFF", ha="center", va="center")

    # 3A: Grafana (Left side of Observability)
    draw_card(ax, 0.260, 0.055, 0.115, 0.250, bg_color="#FFFFFF", border_color="#86EFAC", radius=0.009)
    ax.text(0.268, 0.280, "Grafana UI", fontsize=9.5, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.268, 0.260, "Port 3000", fontsize=7.8, color="#64748B", va="center")
    ax.text(0.268, 0.232, "• Live RPS", fontsize=8, color="#334155", va="center")
    ax.text(0.268, 0.210, "• P50 / P95 Latency", fontsize=8, color="#334155", va="center")
    ax.text(0.268, 0.188, "• Active Pods", fontsize=8, color="#334155", va="center")
    ax.text(0.268, 0.166, "• SLA Violations %", fontsize=8, color="#334155", va="center")
    ax.text(0.268, 0.144, "• CPU / RAM", fontsize=8, color="#334155", va="center")
    ax.text(0.268, 0.100, "[Preconfigured\nDashboard CM]", fontsize=7.8, fontweight="bold", color="#15803D", va="center")

    # 3B: Prometheus TSDB (Right side of Observability - Immediately Adjacent to Autoscaler!)
    draw_card(ax, 0.390, 0.055, 0.245, 0.250, bg_color="#FFFFFF", border_color="#86EFAC", radius=0.009)
    ax.text(0.400, 0.280, "Prometheus Time-Series Engine", fontsize=10, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.400, 0.260, "Service: prometheus:9090 (v2.45.0)", fontsize=7.8, color="#64748B", va="center")
    ax.text(0.400, 0.235, "• Kube SD: role: pod, annotation scrape=true", fontsize=8, color="#334155", va="center")
    ax.text(0.400, 0.215, "• High-Frequency Scrape: interval = 3 seconds", fontsize=8, color="#15803D", fontweight="bold", va="center")
    ax.text(0.400, 0.195, "• Metric Scraped: http_requests_total{route}", fontsize=8, color="#334155", va="center")

    draw_card(ax, 0.400, 0.075, 0.225, 0.100, bg_color="#F8FAFC", border_color="#CBD5E1", radius=0.006, shadow=False)
    ax.text(0.5125, 0.150, "Real-Time PromQL Rate Query:", fontsize=8, fontweight="bold", color="#0F172A", ha="center", va="center")
    ax.text(0.5125, 0.125, 'sum(rate(http_requests_total[30s]))', fontsize=8, fontweight="bold", color="#DC2626", ha="center", va="center")
    ax.text(0.5125, 0.098, 'Sliding Arrival Rate: W_t (requests/sec)', fontsize=7.5, color="#2563EB", ha="center", va="center")

    # =========================================================================
    # 4. ZONE 4: AI PREDICTIVE AUTOSCALER (MAPE-K LOOP) (RIGHT)
    # =========================================================================
    draw_card(ax, 0.670, 0.04, 0.310, 0.855, bg_color="#FAF5FF", border_color="#E9D5FF", border_width=1.6, radius=0.012)
    
    # Header Badge
    draw_card(ax, 0.680, 0.845, 0.290, 0.038, bg_color="#7E22CE", border_color="#6B21A8", radius=0.007, shadow=False)
    ax.text(0.825, 0.864, "4. AI PREDICTIVE AUTOSCALER (MAPE-K LOOP)", fontsize=10.5, fontweight="bold", color="#FFFFFF", ha="center", va="center")

    # 4A: M - MONITOR
    draw_card(ax, 0.685, 0.705, 0.280, 0.125, bg_color="#FFFFFF", border_color="#D8B4FE", radius=0.009)
    ax.text(0.695, 0.805, "M: MONITOR (Telemetry Ingestion)", fontsize=10, fontweight="bold", color="#6B21A8", va="center")
    ax.text(0.695, 0.782, "• Prometheus HTTP API Client (Poll Interval T = 3s)", fontsize=8.2, color="#334155", va="center")
    ax.text(0.695, 0.762, "• Sliding Lookback Buffer: Window of k = 12 steps", fontsize=8.2, color="#334155", va="center")
    ax.text(0.695, 0.742, "• State Vector: [W_(t-11), W_(t-10), ..., W_t]", fontsize=8.2, color="#2563EB", fontweight="bold", va="center")
    ax.text(0.695, 0.720, "• In-Cluster Fallback: Direct kubectl exec query", fontsize=7.8, color="#64748B", va="center")

    # 4B: A - ANALYZE (Model Zoo)
    draw_card(ax, 0.685, 0.445, 0.280, 0.245, bg_color="#FFFFFF", border_color="#D8B4FE", radius=0.009)
    ax.text(0.695, 0.665, "A: ANALYZE (Plug-and-Play Model Zoo)", fontsize=10, fontweight="bold", color="#6B21A8", va="center")
    ax.text(0.695, 0.645, "Universal Interface: BaseWorkloadModel", fontsize=7.8, color="#64748B", va="center")

    draw_card(ax, 0.695, 0.485, 0.260, 0.150, bg_color="#F8FAFC", border_color="#E2E8F0", radius=0.007, shadow=False)
    ax.text(0.705, 0.615, "Evaluated AI Architectures:", fontsize=8.2, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.705, 0.595, "• Bi-LSTM: 2-layer bidir (137k param, MAPE 8.12%)", fontsize=7.5, color="#1E293B", fontweight="bold", va="center")
    ax.text(0.705, 0.575, "• GRU: 2-layer gated (39k param, Live P95: 9.7ms) ◄", fontsize=7.5, color="#15803D", fontweight="bold", va="center")
    ax.text(0.705, 0.555, "• Standard LSTM / Transformer / MLP", fontsize=7.5, color="#334155", va="center")
    ax.text(0.705, 0.535, "• Random Forest (100 estimators) / Ridge Regressor", fontsize=7.5, color="#B45309", va="center")
    ax.text(0.705, 0.505, "MinMaxScaler Inverse Transform → W_hat_(t+1) (RPS)", fontsize=7.8, color="#7E22CE", fontweight="bold", va="center")

    ax.text(0.695, 0.463, "Output: Next-step predicted arrival rate W_hat_(t+1)", fontsize=8.2, fontweight="bold", color="#DC2626", va="center")

    # 4C: P - PLAN (Adaption Manager)
    draw_card(ax, 0.685, 0.210, 0.280, 0.220, bg_color="#FFFFFF", border_color="#D8B4FE", radius=0.009)
    ax.text(0.695, 0.405, "P: PLAN (Capacity-Based Adaption Manager)", fontsize=10, fontweight="bold", color="#6B21A8", va="center")
    ax.text(0.695, 0.385, "Formulation: Dang-Quang & Yoo (Appl. Sci. 2021)", fontsize=7.8, color="#64748B", va="center")

    draw_card(ax, 0.695, 0.290, 0.260, 0.085, bg_color="#FEF2F2", border_color="#FECACA", radius=0.006, shadow=False)
    ax.text(0.825, 0.350, r"$R_{target} = \max\left(R_{min}, \min\left(R_{max}, \lceil \hat{W}_{t+1} / C_{pod} \rceil \right)\right)$", fontsize=8.8, fontweight="bold", color="#991B1B", ha="center", va="center")
    ax.text(0.825, 0.312, r"C_pod = 50 req/s • R_min = 1 • R_max = 8", fontsize=7.5, color="#7F1D1D", ha="center", va="center")

    ax.text(0.695, 0.268, "1. Proactive Scale-Out: Immediate if R_target > R_curr", fontsize=7.8, fontweight="bold", color="#DC2626", va="center")
    ax.text(0.695, 0.248, "2. Cooldown Time: Hold pods for CDT = 30 seconds", fontsize=7.8, color="#B45309", va="center")
    ax.text(0.695, 0.228, "3. Anti-Thrashing RRS: Shed max(1, ceil(Surplus * 0.5))", fontsize=7.8, color="#15803D", va="center")

    # 4D: E & K - EXECUTE & KNOWLEDGE BASE
    draw_card(ax, 0.685, 0.055, 0.280, 0.140, bg_color="#FFFFFF", border_color="#D8B4FE", radius=0.009)
    ax.text(0.695, 0.170, "E: EXECUTE & K: KNOWLEDGE", fontsize=10, fontweight="bold", color="#6B21A8", va="center")
    ax.text(0.695, 0.148, "• Execute: PATCH /apis/apps/v1/.../fibserver/scale", fontsize=8.2, fontweight="bold", color="#0F172A", va="center")
    ax.text(0.695, 0.128, "• Command: kubectl scale --replicas=R_target", fontsize=7.8, color="#475569", va="center")
    ax.text(0.695, 0.103, "• Knowledge Base: Checkpoints (pt/pkl), Scaler,", fontsize=8, color="#334155", va="center")
    ax.text(0.695, 0.083, "  Live telemetry logs (autoscaler_telemetry.jsonl)", fontsize=8, color="#334155", va="center")

    # =========================================================================
    # 5. DATA FLOW ARROWS (100% UNCONGESTED & ORTHOGONALLY ALIGNED)
    # =========================================================================
    # Flow 1: Workload -> Ingress NGINX
    draw_arrow(ax, (0.218, 0.65), (0.260, 0.65), color="#2563EB", width=2.2, label="1. HTTP Traffic\n(/fib/:n)", label_pos=0.5)

    # Flow 2: Ingress NGINX -> Kube-Proxy Service (Across the 0.055 open gap)
    draw_arrow(ax, (0.420, 0.65), (0.475, 0.65), color="#2563EB", width=2.0)

    # Flow 3: Kube-Proxy -> Pods
    draw_arrow(ax, (0.555, 0.585), (0.500, 0.573), color="#2563EB", width=2.0, rad=-0.12, label="2. Load-Balanced\nTraffic Pool", label_pos=0.5)

    # Flow 4: Pods -> Prometheus Scraper (Direct vertical flow into Prometheus TSDB at x=0.512)
    draw_arrow(ax, (0.512, 0.398), (0.512, 0.305), color="#15803D", width=2.2, label="3. Metrics Scrape (3s)\n(http_requests_total)", label_pos=0.5)

    # Flow 5: Grafana <- Prometheus (Internal in Observability Zone)
    draw_arrow(ax, (0.390, 0.180), (0.375, 0.180), color="#15803D", width=1.8)

    # Flow 6: Prometheus -> MAPE-K Monitor (Routed with label cleanly adjacent to Monitor entrance)
    draw_arrow(ax, (0.635, 0.220), (0.685, 0.770), color="#7E22CE", width=2.2, rad=0.10, label="4. PromQL Query\nsum(rate[30s])", label_pos=0.88)

    # Flow 7: Monitor -> Analyze
    draw_arrow(ax, (0.825, 0.705), (0.825, 0.690), color="#7E22CE", width=2.0)

    # Flow 8: Analyze -> Plan
    draw_arrow(ax, (0.825, 0.445), (0.825, 0.430), color="#7E22CE", width=2.0, label="W_hat_(t+1)", label_pos=0.5)

    # Flow 9: Plan -> Execute
    draw_arrow(ax, (0.825, 0.210), (0.825, 0.195), color="#7E22CE", width=2.0, label="R_target", label_pos=0.5)

    # Flow 10: Execute -> Kubernetes Control Plane (kube-apiserver) -> Feedback Loop Closed!
    draw_arrow(ax, (0.685, 0.125), (0.635, 0.775), color="#DC2626", width=2.5, rad=-0.16, label="5. Scale Action\n(PATCH spec.replicas)", label_pos=0.84)

    # Flow 11: Control plane scales Pods (Straight down through corridor between Ingress & Kube-Proxy)
    draw_arrow(ax, (0.4475, 0.725), (0.4475, 0.573), color="#DC2626", width=2.2, label="6. Reconcile\nReplicas", label_pos=0.50)

    # Output file
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "system_architecture_diagram.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, facecolor="#F8FAFC", edgecolor="none")
    plt.close()
    print(f"[SUCCESS] Pristine ultra-high-resolution architecture diagram generated at:\n  {output_path}")


if __name__ == "__main__":
    main()
