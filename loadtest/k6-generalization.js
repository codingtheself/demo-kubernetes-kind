import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Trend, Rate } from "k6/metrics";

// Custom Telemetry Metrics for Research Evaluation
const fibComputations = new Counter("fib_computations");
const fibLatency = new Trend("fib_latency_ms", true);
const slaViolations = new Rate("sla_violations"); // SLA threshold breached (> 1000ms)
const errors = new Rate("request_errors");

const SLA_THRESHOLD_MS = 1000.0;
const PROFILE = __ENV.PROFILE || "flashcrowd"; // "flashcrowd" | "diurnal" | "bursty"

// Define Traffic Profiles
const profiles = {
  // 1. Sudden Flash Crowd (Sharp step increase to test predictive provisioning under bursts)
  flashcrowd: [
    { duration: "25s", target: 2 },   // Steady low baseline (~40 RPS)
    { duration: "10s", target: 9 },   // Rapid surge (~200+ RPS)
    { duration: "40s", target: 9 },   // Sustained high load (~200-240 RPS)
    { duration: "15s", target: 2 },   // Traffic drop (~40 RPS)
    { duration: "40s", target: 2 },   // Cooldown observation window
  ],
  // 2. Diurnal Wave (Smooth multi-phase load ramp mimicking daily business patterns)
  diurnal: [
    { duration: "20s", target: 2 },   // Overnight trough (~40 RPS)
    { duration: "30s", target: 5 },   // Morning ramp (~110 RPS)
    { duration: "30s", target: 8 },   // Midday peak (~180-200 RPS)
    { duration: "30s", target: 4 },   // Evening decline (~90 RPS)
    { duration: "20s", target: 1 },   // Night base (~25 RPS)
  ],
  // 3. Stochastic Bursty (Oscillating micro-spikes to test CDT and RRS anti-thrashing)
  bursty: [
    { duration: "15s", target: 2 },
    { duration: "15s", target: 8 },
    { duration: "20s", target: 3 },
    { duration: "15s", target: 9 },
    { duration: "25s", target: 2 },
  ],
  // 4. Quick Burst (Fast 55s test: 15s baseline -> 5s surge -> 20s sustained -> 5s drop -> 10s cooldown)
  quickburst: [
    { duration: "15s", target: 2 },
    { duration: "5s", target: 8 },
    { duration: "20s", target: 8 },
    { duration: "5s", target: 2 },
    { duration: "10s", target: 2 },
  ],
};

export const options = {
  stages: profiles[PROFILE] || profiles.flashcrowd,
  thresholds: {
    request_errors: ["rate<0.05"], // Error rate must stay below 5%
  },
};

const BASE_URL = __ENV.BASE_URL || "http://fibserver";

function pickN() {
  return Math.floor(Math.random() * 6) + 15; // n in [15..20]
}

export default function () {
  const n = pickN();
  const startTime = new Date().getTime();
  
  const res = http.get(`${BASE_URL}/fib/${n}`, {
    tags: { route: "/fib/:n" },
    timeout: "15s",
  });

  const duration = res.timings.duration;
  const isSuccess = check(res, {
    "status is 200": (r) => r.status === 200,
    "has result": (r) => r && r.body && r.body.indexOf('"result"') !== -1,
  });

  if (isSuccess) {
    fibComputations.add(1);
    fibLatency.add(duration);
    slaViolations.add(duration > SLA_THRESHOLD_MS ? 1 : 0);
    errors.add(0);
  } else {
    errors.add(1);
    slaViolations.add(1);
  }

  sleep(0.02);
}

export function handleSummary(data) {
  const httpReqs = data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0;
  const v = (data.metrics.http_req_duration && data.metrics.http_req_duration.values) || {};
  const med = v.med !== undefined ? v.med.toFixed(1) : "n/a";
  const p90 = v["p(90)"] !== undefined ? v["p(90)"].toFixed(1) : "n/a";
  const p95 = v["p(95)"] !== undefined ? v["p(95)"].toFixed(1) : "n/a";
  const avg = v.avg !== undefined ? v.avg.toFixed(1) : "n/a";
  const errorRate = (data.metrics.request_errors ? data.metrics.request_errors.values.rate * 100 : 0).toFixed(2);
  const slaRate = (data.metrics.sla_violations ? data.metrics.sla_violations.values.rate * 100 : 0).toFixed(2);

  const stdout = `\n` +
    `===================================================================\n` +
    `  GENERALIZATION BENCHMARK SUMMARY [Profile: ${PROFILE.toUpperCase()}]\n` +
    `===================================================================\n` +
    `  Total Requests Processed : ${httpReqs}\n` +
    `  Average Latency          : ${avg} ms\n` +
    `  Median Latency (p50)     : ${med} ms\n` +
    `  P90 Latency              : ${p90} ms\n` +
    `  P95 Latency              : ${p95} ms\n` +
    `  SLA Violation Rate (>1s) : ${slaRate} %\n` +
    `  HTTP Error Rate          : ${errorRate} %\n` +
    `===================================================================\n`;

  const outputFile = __ENV.OUTPUT_FILE || "loadtest/benchmark_summary.json";
  const outputObj = { stdout: stdout };
  outputObj[outputFile] = JSON.stringify(data, null, 2);
  return outputObj;
}
