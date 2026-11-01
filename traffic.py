#!/usr/bin/env python3
"""
traffic.py - On-Demand Interactive HTTP Traffic Generator for fibserver

Allows starting, stopping, and modulating artificial load against http://localhost:80/fib/:n
with live real-time rate, latency, and error reporting.

Usage:
  python3 traffic.py --rps 120
  python3 traffic.py --rps 200 --duration 60
  ./cluster.sh traffic 150
"""

import sys
import time
import random
import signal
import argparse
import threading
import urllib.request
from collections import deque

# ANSI Colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

running = True


def signal_handler(sig, frame):
    global running
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class TrafficGenerator:
    def __init__(self, target_url: str = "http://localhost:80", target_rps: float = 100.0, workers: int = 16):
        self.target_url = target_url.rstrip("/")
        self.target_rps = target_rps
        self.workers = workers

        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0

        # Rolling 1-second metrics
        self.latencies = deque(maxlen=500)
        self.recent_timestamps = deque(maxlen=2000)
        self.lock = threading.Lock()

    def worker_loop(self):
        global running
        while running:
            # Pick a realistic n in 15..20 (1-5ms compute time)
            n = random.randint(15, 20)
            url = f"{self.target_url}/fib/{n}"

            t0 = time.perf_counter()
            success = False
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "CustomTrafficGen/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        success = True
            except Exception:
                success = False

            dur_ms = (time.perf_counter() - t0) * 1000.0
            now = time.time()

            with self.lock:
                self.total_requests += 1
                if success:
                    self.successful_requests += 1
                else:
                    self.failed_requests += 1
                self.latencies.append(dur_ms)
                self.recent_timestamps.append(now)

            # Throttle each worker to target RPS
            # sleep time per worker = num_workers / target_rps
            sleep_time = max(0.001, (self.workers / max(1.0, self.target_rps)) - (dur_ms / 1000.0))
            time.sleep(min(0.2, sleep_time))

    def run(self, max_duration: int = 0):
        global running
        threads = []
        for _ in range(self.workers):
            t = threading.Thread(target=self.worker_loop, daemon=True)
            t.start()
            threads.append(t)

        start_time = time.time()
        print(f"\n{BOLD}{CYAN}==================================================================={RESET}")
        print(f"{BOLD}{CYAN}      ON-DEMAND TRAFFIC GENERATOR FOR FIBSERVER (PRESS CTRL+C TO STOP)     {RESET}")
        print(f"{BOLD}{CYAN}==================================================================={RESET}")
        print(f"  Target URL    : {BOLD}{self.target_url}/fib/:n{RESET}")
        print(f"  Target Rate   : {BOLD}{self.target_rps:.1f} req/s{RESET}")
        print(f"  Worker Threads: {BOLD}{self.workers}{RESET}")
        print(f"{CYAN}==================================================================={RESET}\n")

        try:
            while running:
                time.sleep(1.0)
                now = time.time()
                elapsed = now - start_time

                if max_duration > 0 and elapsed >= max_duration:
                    break

                with self.lock:
                    # Filter timestamps within the last 1.0 second
                    cutoff = now - 1.0
                    while self.recent_timestamps and self.recent_timestamps[0] < cutoff:
                        self.recent_timestamps.popleft()
                    current_rate = len(self.recent_timestamps)

                    recent_lats = list(self.latencies)
                    total_reqs = self.total_requests
                    failed = self.failed_requests

                if recent_lats:
                    avg_lat = sum(recent_lats) / len(recent_lats)
                    sorted_lats = sorted(recent_lats)
                    p95_idx = int(len(sorted_lats) * 0.95)
                    p95_lat = sorted_lats[min(p95_idx, len(sorted_lats) - 1)]
                else:
                    avg_lat = 0.0
                    p95_lat = 0.0

                err_rate = (failed / max(1, total_reqs)) * 100.0

                status_color = GREEN if err_rate < 2.0 else RED
                print(
                    f"\r[{time.strftime('%H:%M:%S')}] {BOLD}🚀 Traffic: {current_rate:>5.1f} req/s{RESET} | "
                    f"Total Sent: {total_reqs:>6} | "
                    f"Avg Lat: {avg_lat:>5.1f}ms | "
                    f"P95: {p95_lat:>5.1f}ms | "
                    f"Errors: {status_color}{err_rate:>4.1f}%{RESET}",
                    end="",
                    flush=True
                )

        finally:
            running = False
            total_time = max(0.1, time.time() - start_time)
            print("\n")
            print(f"{BOLD}{CYAN}--- Final Traffic Summary ---{RESET}")
            print(f"  Duration           : {total_time:.1f}s")
            print(f"  Total Requests     : {self.total_requests:,}")
            print(f"  Successful (200 OK): {self.successful_requests:,}")
            print(f"  Failed Requests    : {self.failed_requests:,}")
            print(f"  Average Throughput : {self.total_requests / total_time:.1f} req/s")
            if self.latencies:
                all_lats = sorted(list(self.latencies))
                print(f"  Overall Avg Latency: {sum(all_lats) / len(all_lats):.2f} ms")
                print(f"  Overall P95 Latency: {all_lats[int(len(all_lats) * 0.95)]:.2f} ms")
            print(f"{CYAN}----------------------------{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate artificial HTTP traffic to fibserver")
    parser.add_argument("--url", type=str, default="http://localhost:80", help="Base URL of fibserver")
    parser.add_argument("--rps", type=float, default=120.0, help="Target Requests Per Second (default: 120)")
    parser.add_argument("--workers", type=int, default=24, help="Number of concurrent worker threads")
    parser.add_argument("--duration", type=int, default=0, help="Duration in seconds (0 = run indefinitely until Ctrl+C)")
    args = parser.parse_args()

    gen = TrafficGenerator(target_url=args.url, target_rps=args.rps, workers=args.workers)
    gen.run(max_duration=args.duration)


if __name__ == "__main__":
    main()
