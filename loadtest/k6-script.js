import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend, Rate } from "k6/metrics";

// Custom metrics (appear in the k6 summary)
const fibComputations = new Counter("fib_computations");
const fibLatency = new Trend("fib_latency_ms", true);
const errors = new Rate("fib_errors");

export const options = {
  // Staged ramp: start low, ramp to a plateau, then spike, then recover.
  // This is what actually provokes the HPA: sustained CPU above target.
  stages: [
    { duration: "30s", target: 2 },   // warm-up / baseline
    { duration: "60s", target: 20 },  // ramp into saturation
    { duration: "120s", target: 20 }, // sustained plateau (HPA should be at max)
    { duration: "30s", target: 60 },  // spike burst
    { duration: "30s", target: 2 },   // recovery (HPA should scale back down)
  ],
  thresholds: {
    // Pass/fail criteria — k6 exits non-zero if these are breached.
    http_req_failed: ["rate<0.05"],                  // < 5% errors
    http_req_duration: ["p(95)<15000"],              // p95 under 15s
    fib_errors: ["rate<0.05"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://fibserver";

// Keep n moderate so each request finishes in a reasonable time but still
// burns real CPU. fib(32) ~ 100ms, fib(36) ~ 1s of pure CPU per request.
function pickN() {
  return Math.floor(Math.random() * 5) + 32; // 32..36
}

export default function () {
  const n = pickN();
  const res = http.get(`${BASE_URL}/fib/${n}`, {
    tags: { route: "/fib/:n" },
    timeout: "60s",
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

  sleep(0.1);
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