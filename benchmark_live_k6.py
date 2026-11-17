#!/usr/bin/env python3
"""
benchmark_live_k6.py - Automated End-to-End Live Kubernetes Model Benchmark

Orchestrates comparing AI Predictive Autoscaler models (Bi-LSTM, GRU, LSTM,
Transformer, MLP, Ridge, Random Forest) and Baseline in a live Kubernetes cluster
under identical, repeatable k6 load testing profiles.

Pipeline for each model:
  1. Reset cluster to clean baseline (scale fibserver to 1 replica).
  2. Launch AI Autoscaler with target model in background.
  3. Warm up Prometheus scraping and autoscaler sliding window.
  4. Trigger k6 load test container with chosen traffic profile.
  5. Concurrently record time-series telemetry (RPS, predictions, replicas, ready pods).
  6. Collect k6 SLA violations, P95 latency, and error metrics.
  7. Export telemetry CSV, summary JSON, and composite leaderboard.
"""

import os
import sys

# Auto re-exec into local virtualenv if dependencies are in .venv
VENV_PYTHON = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    try:
        import numpy  # noqa: F401
    except ImportError:
        os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

import time
import json
import csv
import signal
import urllib.request
import urllib.parse
import argparse
import subprocess
import threading
from typing import Dict, Any, List

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from model_zoo.registry import list_available_models

# ANSI Styling
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def run_cmd(cmd: List[str], check: bool = True, timeout: int = 60) -> str:
    """Run subprocess command and return decoded output."""
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check, timeout=timeout)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        if check:
            print(f"{RED}[ERROR] Command failed: {' '.join(cmd)}\nStderr: {e.stderr}{RESET}")
            raise
        return ""


def get_current_replicas(deployment: str = "fibserver", namespace: str = "default") -> int:
    try:
        cmd = ["kubectl", "get", "deployment", deployment, "-n", namespace, "-o", "jsonpath={.spec.replicas}"]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return int(out) if out else 1
    except Exception:
        return 1


def get_ready_replicas(deployment: str = "fibserver", namespace: str = "default") -> int:
    try:
        cmd = ["kubectl", "get", "deployment", deployment, "-n", namespace, "-o", "jsonpath={.status.readyReplicas}"]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return int(out) if out else 0
    except Exception:
        return 0


def get_prometheus_rps(prom_url: str, window: str = "15s") -> float:
    promql = f"sum(rate(http_requests_total[{window}]))"
    query_url = f"{prom_url.rstrip('/')}/api/v1/query?query={urllib.parse.quote(promql)}"
    try:
        req = urllib.request.Request(query_url, headers={"User-Agent": "LiveBenchmarkRunner/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                results = data.get("data", {}).get("result", [])
                if results:
                    return max(0.0, float(results[0]["value"][1]))
    except Exception:
        pass
    return 0.0


def reset_cluster(deployment: str = "fibserver", namespace: str = "default", cooldown: int = 10):
    """Reset fibserver to 1 replica and wait until ready."""
    print(f"{CYAN}[RESET] Scaling {deployment} to 1 replica...{RESET}", end="", flush=True)
    subprocess.run(["kubectl", "scale", f"deployment/{deployment}", "-n", namespace, "--replicas=1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait for rollout
    subprocess.run(["kubectl", "rollout", "status", f"deployment/{deployment}", "-n", namespace, "--timeout=45s"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(cooldown)
    print(f" {GREEN}Ready (1 replica active).{RESET}")


class LiveTelemetryRecorder:
    """Records second-by-second in-cluster telemetry during a load test."""
    def __init__(self, prom_url: str, deployment: str = "fibserver", namespace: str = "default", sample_interval: float = 1.0):
        self.prom_url = prom_url
        self.deployment = deployment
        self.namespace = namespace
        self.sample_interval = sample_interval
        self.running = False
        self.samples = []
        self._thread = None
        self.start_epoch = None

    def _loop(self):
        while self.running:
            t_now = time.time()
            elapsed = t_now - self.start_epoch if self.start_epoch else 0.0
            rps = get_prometheus_rps(self.prom_url, window="30s")
            spec_rep = get_current_replicas(self.deployment, self.namespace)
            ready_rep = get_ready_replicas(self.deployment, self.namespace)

            self.samples.append({
                "timestamp": t_now,
                "elapsed_sec": round(elapsed, 2),
                "measured_rps": round(rps, 2),
                "spec_replicas": spec_rep,
                "ready_replicas": ready_rep,
            })
            time.sleep(self.sample_interval)

    def start(self):
        self.running = True
        self.start_epoch = time.time()
        self.samples = []
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> List[Dict[str, Any]]:
        self.running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        return self.samples


def get_service_url() -> str:
    """Resolve fibserver Service ClusterIP for direct in-cluster routing."""
    try:
        cmd = ["kubectl", "get", "svc", "fibserver", "-o", "jsonpath={.spec.clusterIP}"]
        ip = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        if ip:
            return f"http://{ip}"
    except Exception:
        pass
    return "http://localhost:80"


def run_k6_docker(profile: str, target_url: str, summary_file: str) -> bool:
    """Run k6 inside docker container against the target URL."""
    abs_summary = os.path.abspath(summary_file)
    os.makedirs(os.path.dirname(abs_summary), exist_ok=True)
    try:
        os.chmod(os.path.dirname(abs_summary), 0o777)
    except Exception:
        pass

    # If target is localhost, use direct ClusterIP through Kind's container network namespace
    network = "container:kind-control-plane"
    if "localhost" in target_url or "127.0.0.1" in target_url:
        actual_target = get_service_url()
    else:
        actual_target = target_url

    cmd = [
        "docker", "run", "--rm",
        f"--network={network}",
        "-v", f"{ROOT_DIR}:/workspace:z",
        "-w", "/workspace",
        "-e", f"BASE_URL={actual_target}",
        "-e", f"PROFILE={profile}",
        "-e", f"OUTPUT_FILE={os.path.relpath(abs_summary, ROOT_DIR)}",
        "docker.io/grafana/k6:0.53.0",
        "run", "--quiet",
        "loadtest/k6-generalization.js"
    ]

    print(f"{CYAN}[LOAD] Running k6 load test [Profile: {BOLD}{profile.upper()}{RESET}{CYAN}] -> {actual_target}...{RESET}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.stdout:
        # Print summary section
        lines = res.stdout.splitlines()
        for line in lines:
            if "GENERALIZATION BENCHMARK SUMMARY" in line or "Total Requests" in line or "Latency" in line or "SLA" in line or "Error" in line:
                print(f"  {line}")
    return res.returncode == 0


def evaluate_single_model(
    model_name: str,
    profile: str,
    target_url: str,
    prom_url: str,
    pod_capacity: float,
    cooldown: int,
    interval: int,
    warmup: int,
    output_dir: str,
) -> Dict[str, Any]:
    """Execute live evaluation for a single autoscaler model."""
    print(f"\n{BOLD}{MAGENTA}{'='*68}{RESET}")
    print(f"{BOLD}{MAGENTA}   LIVE IN-CLUSTER BENCHMARK: {model_name.upper()}{RESET}")
    print(f"{BOLD}{MAGENTA}{'='*68}{RESET}")

    model_dir = os.path.join(output_dir, model_name)
    os.makedirs(model_dir, exist_ok=True)
    telemetry_file = os.path.join(model_dir, "autoscaler_telemetry.jsonl")
    k6_summary_file = os.path.join(model_dir, "k6_summary.json")
    cluster_telemetry_csv = os.path.join(model_dir, "cluster_telemetry.csv")

    # Clean old files
    for f in [telemetry_file, k6_summary_file, cluster_telemetry_csv]:
        if os.path.exists(f):
            os.remove(f)

    # 1. Reset cluster
    reset_cluster(cooldown=8)

    # 2. Launch Autoscaler Process
    scaler_proc = None
    if model_name != "baseline_static":
        scaler_cmd = [
            sys.executable,
            os.path.join(ROOT_DIR, "predictive_autoscaler.py"),
            "--model-type", model_name,
            "--pod-capacity", str(pod_capacity),
            "--cooldown", str(cooldown),
            "--interval", str(interval),
            "--prom-url", prom_url,
            "--query-window", "30s",
            "--telemetry-file", telemetry_file,
        ]
        scaler_log = open(os.path.join(model_dir, "autoscaler.log"), "w")
        scaler_proc = subprocess.Popen(scaler_cmd, stdout=scaler_log, stderr=subprocess.STDOUT)
        print(f"{GREEN}✓ Autoscaler launched (PID: {scaler_proc.pid}) with model '{model_name}'.{RESET}")
    else:
        print(f"{YELLOW}✓ Running baseline (static 1 replica, no autoscaler).{RESET}")

    # 3. Warm-up
    print(f"{CYAN}[WARMUP] Waiting {warmup}s for metrics pipeline synchronization...{RESET}")
    time.sleep(warmup)

    # 4. Start Telemetry Recorder
    recorder = LiveTelemetryRecorder(prom_url=prom_url, sample_interval=1.0)
    recorder.start()

    # 5. Run k6 Load Test
    k6_success = run_k6_docker(profile=profile, target_url=target_url, summary_file=k6_summary_file)

    # 6. Stop Telemetry & Autoscaler
    samples = recorder.stop()
    if scaler_proc:
        try:
            scaler_proc.send_signal(signal.SIGINT)
            scaler_proc.wait(timeout=5)
        except Exception:
            scaler_proc.kill()
        scaler_log.close()
        print(f"{CYAN}✓ Autoscaler process stopped.{RESET}")

    # 7. Write Cluster Telemetry CSV
    if samples:
        with open(cluster_telemetry_csv, "w", newline="") as cf:
            writer = csv.DictWriter(cf, fieldnames=list(samples[0].keys()))
            writer.writeheader()
            writer.writerows(samples)

    # 8. Parse k6 Summary Metrics
    k6_metrics = {}
    if os.path.exists(k6_summary_file):
        try:
            with open(k6_summary_file, "r") as kf:
                raw_k6 = json.load(kf)
                m = raw_k6.get("metrics", {})
                reqs = m.get("http_reqs", {}).get("values", {})
                dur = m.get("http_req_duration", {}).get("values", {})
                sla = m.get("sla_violations", {}).get("values", {})
                err = m.get("request_errors", {}).get("values", {})

                k6_metrics = {
                    "total_requests": int(reqs.get("count", 0)),
                    "throughput_rps": round(reqs.get("rate", 0.0), 1),
                    "avg_latency_ms": round(dur.get("avg", 0.0), 2),
                    "med_latency_ms": round(dur.get("med", 0.0), 2),
                    "p90_latency_ms": round(dur.get("p(90)", 0.0), 2),
                    "p95_latency_ms": round(dur.get("p(95)", 0.0), 2),
                    "max_latency_ms": round(dur.get("max", 0.0), 2),
                    "sla_violations_pct": round(sla.get("rate", 0.0) * 100.0, 2),
                    "error_rate_pct": round(err.get("rate", 0.0) * 100.0, 2),
                }
        except Exception as e:
            print(f"{YELLOW}[WARN] Failed to parse k6 summary: {e}{RESET}")

    # 9. Compute Cluster Pod Utilization Metrics
    spec_reps = [s["spec_replicas"] for s in samples] if samples else [1]
    ready_reps = [s["ready_replicas"] for s in samples] if samples else [1]
    avg_reps = round(sum(spec_reps) / max(1, len(spec_reps)), 2)
    peak_reps = max(spec_reps)
    pod_seconds = round(sum(spec_reps) * 1.0, 1)

    # Reaction Time: time from surge (measured RPS > 50) until spec_replicas > 1
    reaction_time = None
    surge_start = None
    for s in samples:
        if surge_start is None and s["measured_rps"] >= 50.0:
            surge_start = s["elapsed_sec"]
        if surge_start is not None and s["spec_replicas"] > 1:
            reaction_time = round(s["elapsed_sec"] - surge_start, 1)
            break

    summary = {
        "model": model_name,
        "profile": profile,
        **k6_metrics,
        "avg_replicas": avg_reps,
        "peak_replicas": peak_reps,
        "pod_seconds": pod_seconds,
        "reaction_time_s": reaction_time if reaction_time is not None else -1.0,
    }

    # Save consolidated model summary
    with open(os.path.join(model_dir, "summary.json"), "w") as sf:
        json.dump(summary, sf, indent=2)

    return summary


def generate_leaderboard(results: List[Dict[str, Any]], output_dir: str):
    """Sort and export live benchmark leaderboard in Markdown and CSV."""
    if not results:
        return

    # Multi-criteria ranking:
    # 1. SLA Violation Rate (%) ascending
    # 2. P95 Latency (ms) ascending
    # 3. HTTP Error Rate (%) ascending
    # 4. Pod Seconds (cost) ascending
    sorted_results = sorted(
        results,
        key=lambda r: (
            r.get("sla_violations_pct", 100.0),
            r.get("p95_latency_ms", 99999.0),
            r.get("error_rate_pct", 100.0),
            r.get("pod_seconds", 99999.0),
        )
    )

    # Export CSV
    csv_path = os.path.join(output_dir, "live_benchmark_leaderboard.csv")
    fields = [
        "rank", "model", "sla_violations_pct", "p95_latency_ms", "med_latency_ms",
        "avg_latency_ms", "error_rate_pct", "avg_replicas", "peak_replicas",
        "pod_seconds", "reaction_time_s", "total_requests"
    ]
    with open(csv_path, "w", newline="") as cf:
        writer = csv.DictWriter(cf, fieldnames=fields)
        writer.writeheader()
        for idx, r in enumerate(sorted_results, 1):
            row = {"rank": idx, **r}
            writer.writerow({k: row.get(k, "") for k in fields})

    # Export Markdown
    md_path = os.path.join(output_dir, "live_benchmark_leaderboard.md")
    with open(md_path, "w") as mf:
        mf.write("# Live In-Cluster Kubernetes Benchmark Leaderboard\n\n")
        mf.write(f"Evaluated under real traffic using `k6` on Kubernetes Kind with Dang-Quang & Yoo Capacity-Based Dimensioning.\n\n")
        mf.write("| Rank | Model Architecture | SLA Violations (>1s) | P95 Latency | P50 (Med) | Error Rate | Avg Replicas | Peak Replicas | Pod-Seconds | Reaction Time |\n")
        mf.write("|:----:|:-------------------|:--------------------:|:-----------:|:---------:|:----------:|:------------:|:-------------:|:-----------:|:-------------:|\n")
        for idx, r in enumerate(sorted_results, 1):
            sla_str = f"**{r.get('sla_violations_pct', 0.0):.2f}%**"
            p95_str = f"{r.get('p95_latency_ms', 0.0):.1f} ms"
            med_str = f"{r.get('med_latency_ms', 0.0):.1f} ms"
            err_str = f"{r.get('error_rate_pct', 0.0):.2f}%"
            react_str = f"{r.get('reaction_time_s', -1.0):.1f}s" if r.get('reaction_time_s', -1.0) >= 0 else "N/A"
            mf.write(f"| {idx} | `{r['model'].upper()}` | {sla_str} | {p95_str} | {med_str} | {err_str} | {r.get('avg_replicas', 0.0):.1f} | {r.get('peak_replicas', 1)} | {r.get('pod_seconds', 0.0):.0f} | {react_str} |\n")

        mf.write("\n### Ranking Methodology\n")
        mf.write("1. **SLA Violations Rate (Primary)**: Percentage of HTTP requests exceeding the 1000ms service level objective.\n")
        mf.write("2. **P95 Latency (Secondary)**: 95th percentile latency experienced by real clients during peak traffic bursts.\n")
        mf.write("3. **Error Rate**: Percentage of HTTP 5xx failures or connection timeouts.\n")
        mf.write("4. **Resource Cost**: Total Pod-Seconds consumed over the test lifecycle.\n")

    print(f"\n{GREEN}{BOLD}✓ Live benchmark results exported:{RESET}")
    print(f"  CSV : {BOLD}{csv_path}{RESET}")
    print(f"  MD  : {BOLD}{md_path}{RESET}")


def main():
    parser = argparse.ArgumentParser(description="Automated Live Kubernetes Autoscaler Benchmark with k6")
    parser.add_argument(
        "--models",
        type=str,
        default="bilstm,gru,ridge,random_forest,baseline_static",
        help="Comma-separated list of models to evaluate (default: bilstm,gru,ridge,random_forest,baseline_static)"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="quickburst",
        choices=["quickburst", "flashcrowd", "bursty", "diurnal"],
        help="k6 traffic profile (default: quickburst [55s])"
    )
    parser.add_argument(
        "--target-url",
        type=str,
        default="http://localhost:80",
        help="Target fibserver API endpoint (default: http://localhost:80)"
    )
    parser.add_argument(
        "--prom-url",
        type=str,
        default="http://localhost:9090",
        help="Prometheus Base URL (default: http://localhost:9090)"
    )
    parser.add_argument(
        "--pod-capacity",
        type=float,
        default=50.0,
        help="Single pod throughput capacity (default: 50.0 req/s)"
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=30,
        help="Autoscaler cooldown time CDT in seconds (default: 30)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=3,
        help="Autoscaler poll interval in seconds (default: 3)"
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=8,
        help="Warmup wait seconds before starting k6 load (default: 8)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="models/live_benchmarks",
        help="Output directory for live benchmark telemetry and summaries"
    )

    args = parser.parse_args()
    model_list = [m.strip().lower() for m in args.models.split(",") if m.strip()]

    print(f"\n{BOLD}{CYAN}==================================================================={RESET}")
    print(f"{BOLD}{CYAN}      LIVE KUBERNETES AI AUTOSCALER BENCHMARK SUITE (k6)          {RESET}")
    print(f"{BOLD}{CYAN}==================================================================={RESET}")
    print(f"  Target URL      : {BOLD}{args.target_url}{RESET}")
    print(f"  Prometheus URL  : {BOLD}{args.prom_url}{RESET}")
    print(f"  Traffic Profile : {BOLD}{args.profile.upper()}{RESET}")
    print(f"  Models to Test  : {BOLD}{', '.join(model_list)}{RESET}")
    print(f"  Pod Capacity    : {BOLD}{args.pod_capacity} req/s per replica{RESET}")
    print(f"  Output Directory: {BOLD}{args.output_dir}{RESET}")
    print(f"{CYAN}==================================================================={RESET}\n")

    os.makedirs(args.output_dir, exist_ok=True)
    all_results = []

    for model in model_list:
        try:
            summary = evaluate_single_model(
                model_name=model,
                profile=args.profile,
                target_url=args.target_url,
                prom_url=args.prom_url,
                pod_capacity=args.pod_capacity,
                cooldown=args.cooldown,
                interval=args.interval,
                warmup=args.warmup,
                output_dir=args.output_dir,
            )
            all_results.append(summary)
        except Exception as e:
            print(f"{RED}[ERROR] Evaluation failed for model '{model}': {e}{RESET}")

    generate_leaderboard(all_results, args.output_dir)

    # Automatically generate plots
    try:
        plot_script = os.path.join(ROOT_DIR, "plot_live_benchmarks.py")
        if os.path.exists(plot_script):
            print(f"\n{CYAN}[PLOTS] Generating live benchmark comparison figures...{RESET}")
            subprocess.run([sys.executable, plot_script, "--data-dir", args.output_dir], check=True)
    except Exception as e:
        print(f"{YELLOW}[WARN] Plot generation failed: {e}{RESET}")


if __name__ == "__main__":
    main()
