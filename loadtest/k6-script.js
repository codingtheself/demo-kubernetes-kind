import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend, Rate } from "k6/metrics";

// Custom metrics (appear in the k6 summary)
const fibComputations = new Counter("fib_computations");
const fibLatency = new Trend("fib_latency_ms", true);
const errors = new Rate("fib_errors");

export const options = {
  // Staged ramp tuned for 100+ req/s spike autoscaling demonstration
  stages: [
    { duration: "20s", target: 2 },   // Baseline warm-up: ~40-60 RPS (under 100 threshold)
    { duration: "40s", target: 8 },   // Traffic spike: ~150-220 RPS (exceeds 100 threshold -> triggers scale up)
    { duration: "60s", target: 1 },   // Recovery / Low traffic: ~20-30 RPS (under 100 for 60s -> triggers 30s cooldown & scale down)
  ],
  thresholds: {
    // Pass/fail criteria — k6 exits non-zero if these are breached.
    http_req_failed: ["rate<0.05"],                  // < 5% errors
    http_req_duration: ["p(95)<5000"],               // p95 under 5s
    fib_errors: ["rate<0.05"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://fibserver";

// Keep n in 15..20 (~1-5ms per computation).
// This enables generating 100-250 requests/sec cleanly without stalling worker threads.
function pickN() {
  return Math.floor(Math.random() * 6) + 15; // 15..20
}

export default function () {
  const n = pickN();
  const res = http.get(`${BASE_URL}/fib/${n}`, {
    tags: { route: "/fib/:n" },
    timeout: "15s",
  });

  const ok = check(res, {
    "status is 200": (r) => r.status === 200,
    "has result": (r) => r && r.body && r.body.indexOf('"result"') !== -1,
  });

  if (ok) {
    fibComputations.add(1);
    fibLatency.add(res.timings.duration);
  } else {
    errors.add(1);
  }

  sleep(0.02);
}

export function handleSummary(data) {
  const summary = {
    stdout: `\n=== fibserver load test ===\n` +
            `requests:   ${data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0}\n` +
            `p95:        ${data.metrics.http_req_duration ? data.metrics.http_req_duration.values['p(95)'].toFixed(1) : 'n/a'} ms\n` +
            `error rate: ${(data.metrics.http_req_failed ? data.metrics.http_req_failed.values.rate * 100 : 0).toFixed(2)}%\n` +
            `computations: ${data.metrics.fib_computations ? data.metrics.fib_computations.values.count : 0}\n`,
  };
  return summary;
}