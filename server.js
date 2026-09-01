const express = require("express");
const { Worker } = require("worker_threads");
const os = require("os");
const path = require("path");
const client = require("prom-client");

const app = express();

const PORT = 3000;
const POOL_SIZE = Math.max(1, os.cpus().length);

const taskQueue = [];
const workers = [];

client.collectDefaultMetrics({ register: client.register });

const httpRequestsTotal = new client.Counter({
  name: "http_requests_total",
  help: "Total number of HTTP requests",
  labelNames: ["route", "method", "status"]
});

const httpRequestDurationMs = new client.Histogram({
  name: "http_request_duration_ms",
  help: "HTTP request duration in milliseconds",
  labelNames: ["route", "method"],
  buckets: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000]
});

const fibComputationDurationMs = new client.Histogram({
  name: "fib_computation_duration_ms",
  help: "Time spent computing fibonacci(n) in the worker pool, in milliseconds",
  buckets: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000, 1000000]
});

const fibQueueDepth = new client.Gauge({
  name: "fib_queue_depth",
  help: "Number of fibonacci requests waiting for a worker"
});

app.use((req, res, next) => {
  const start = process.hrtime.bigint();

  res.on("finish", () => {
    const end = process.hrtime.bigint();
    const duration = Number(end - start) / 1_000_000;
    const route = (req.route && req.route.path) || req.path;

    httpRequestsTotal.inc({ route, method: req.method, status: res.statusCode });
    httpRequestDurationMs.observe(duration, { route, method: req.method });
  });

  next();
});

function initPool() {
  for (let i = 0; i < POOL_SIZE; i++) {
    const worker = new Worker(path.join(__dirname, "fibWorker.js"));
    worker.busy = false;

    worker.on("message", (result) => {
      const job = worker.job;
      worker.busy = false;
      worker.job = null;
      job.resolve(result);
      processQueue();
    });

    worker.on("error", (err) => {
      const job = worker.job;
      worker.busy = false;
      worker.job = null;
      job.reject(err);
      processQueue();
    });

    workers.push(worker);
  }
}

function processQueue() {
  while (taskQueue.length > 0) {
    const worker = workers.find((w) => !w.busy);
    if (!worker) {
      break;
    }

    const job = taskQueue.shift();
    worker.busy = true;
    worker.job = job;
    worker.postMessage(job.n);
  }

  fibQueueDepth.set(taskQueue.length);
}

function computeFibonacci(n) {
  const job = { n, resolve: null, reject: null };

  const promise = new Promise((resolve, reject) => {
    job.resolve = resolve;
    job.reject = reject;
  });

  taskQueue.push(job);
  fibQueueDepth.set(taskQueue.length);
  processQueue();

  return promise;
}

initPool();

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

app.get("/metrics", async (req, res) => {
  res.set("Content-Type", client.register.contentType);
  res.end(await client.register.metrics());
});

app.get("/fib/:n", async (req, res) => {
  const n = Number(req.params.n);

  if (!Number.isInteger(n) || n < 0) {
    return res.status(400).json({
      error: "n must be non-negative number"
    });
  }

  const start = process.hrtime.bigint();

  let result;
  try {
    result = await computeFibonacci(n);
  } catch (err) {
    return res.status(500).json({ error: "internal error" });
  }

  const end = process.hrtime.bigint();

  const duration = Number(end - start) / 1_000_000;
  fibComputationDurationMs.observe(duration);

  res.json({
    n,
    result,
    duration
  });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Fibonacci server started on port ${PORT} with pool size ${POOL_SIZE}`);
});