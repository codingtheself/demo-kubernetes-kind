const express = require("express");
const { Worker } = require("worker_threads");
const os = require("os");
const path = require("path");
const client = require("prom-client");

const app = express();

const PORT = process.env.PORT ? parseInt(process.env.PORT, 10) : 3000;
const POOL_SIZE = process.env.POOL_SIZE ? parseInt(process.env.POOL_SIZE, 10) : Math.max(1, os.cpus().length);
const COMPUTATION_TIMEOUT_MS = 10000; // 10s hard timeout

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

const httpInflightRequests = new client.Gauge({
  name: "http_inflight_requests",
  help: "Current number of in-flight HTTP requests"
});

app.use((req, res, next) => {
  const start = process.hrtime.bigint();
  httpInflightRequests.inc();

  let finished = false;
  const onFinish = () => {
    if (finished) return;
    finished = true;
    httpInflightRequests.dec();

    const end = process.hrtime.bigint();
    const duration = Number(end - start) / 1_000_000;
    const route = (req.route && req.route.path) || req.path;

    httpRequestsTotal.inc({ route, method: req.method, status: res.statusCode || 499 });
    httpRequestDurationMs.observe(duration, { route, method: req.method });
  };

  res.on("finish", onFinish);
  res.on("close", onFinish);

  next();
});

function createWorker() {
  const worker = new Worker(path.join(__dirname, "fibWorker.js"));
  worker.busy = false;
  worker.job = null;
  worker.timeoutTimer = null;

  worker.on("message", (response) => {
    if (worker.timeoutTimer) {
      clearTimeout(worker.timeoutTimer);
      worker.timeoutTimer = null;
    }

    const job = worker.job;
    worker.busy = false;
    worker.job = null;

    if (job && !job.cancelled) {
      if (response && response.success) {
        job.resolve(response.result);
      } else {
        job.reject(new Error(response?.error || "Worker failed computation"));
      }
    }

    processQueue();
  });

  worker.on("error", (err) => {
    console.error(`Worker error: ${err.message}. Replacing worker...`);
    replaceWorker(worker, err);
  });

  worker.on("exit", (code) => {
    if (code !== 0 && worker.job) {
      console.warn(`Worker exited with code ${code}. Replacing worker...`);
      replaceWorker(worker, new Error(`Worker exited with code ${code}`));
    }
  });

  return worker;
}

function replaceWorker(worker, error) {
  if (worker.timeoutTimer) {
    clearTimeout(worker.timeoutTimer);
    worker.timeoutTimer = null;
  }

  const job = worker.job;
  worker.busy = false;
  worker.job = null;

  const index = workers.indexOf(worker);
  if (index !== -1) {
    workers.splice(index, 1);
  }

  // Terminate running thread immediately to free CPU
  worker.terminate().catch(() => {});

  if (job && !job.cancelled) {
    job.reject(error);
  }

  // Replace with a fresh worker to maintain pool capacity
  const freshWorker = createWorker();
  workers.push(freshWorker);

  processQueue();
}

function initPool() {
  for (let i = 0; i < POOL_SIZE; i++) {
    workers.push(createWorker());
  }
}

function processQueue() {
  while (taskQueue.length > 0) {
    const worker = workers.find((w) => !w.busy);
    if (!worker) {
      break;
    }

    const job = taskQueue.shift();
    if (job.cancelled) {
      continue;
    }

    worker.busy = true;
    worker.job = job;
    job.worker = worker;

    // Start 10-second timeout
    worker.timeoutTimer = setTimeout(() => {
      console.warn(`Computation for n=${job.n} timed out after ${COMPUTATION_TIMEOUT_MS}ms. Terminating worker.`);
      replaceWorker(worker, new Error(`Computation timed out after ${COMPUTATION_TIMEOUT_MS / 1000}s`));
    }, COMPUTATION_TIMEOUT_MS);

    worker.postMessage(job.n);
  }

  fibQueueDepth.set(taskQueue.length);
}

function computeFibonacci(n, cancelRef) {
  let job;

  const promise = new Promise((resolve, reject) => {
    job = {
      n,
      resolve,
      reject,
      cancelled: false,
      worker: null
    };

    taskQueue.push(job);
    fibQueueDepth.set(taskQueue.length);
    processQueue();
  });

  if (cancelRef) {
    cancelRef.cancel = () => {
      if (job.cancelled) return;
      job.cancelled = true;

      // 1. If still waiting in queue, remove it immediately
      const idx = taskQueue.indexOf(job);
      if (idx !== -1) {
        taskQueue.splice(idx, 1);
        fibQueueDepth.set(taskQueue.length);
      }

      // 2. If already executing on a worker, terminate worker immediately to release CPU core
      if (job.worker) {
        console.log(`Client disconnected for n=${n}. Terminating worker and freeing CPU.`);
        replaceWorker(job.worker, new Error("Client disconnected"));
      }

      job.reject(new Error("Client disconnected"));
    };
  }

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

  const cancelRef = {};
  req.on("close", () => {
    if (!res.writableEnded && cancelRef.cancel) {
      cancelRef.cancel();
    }
  });

  const start = process.hrtime.bigint();

  let result;
  try {
    result = await computeFibonacci(n, cancelRef);
  } catch (err) {
    const end = process.hrtime.bigint();
    const duration = Number(end - start) / 1_000_000;
    fibComputationDurationMs.observe(duration);

    if (res.writableEnded) return;

    if (err.message === "Client disconnected") {
      return;
    }

    const isTimeout = err.message && err.message.includes("timed out");
    const statusCode = isTimeout ? 504 : 500;
    return res.status(statusCode).json({ error: err.message || "internal error" });
  }

  const end = process.hrtime.bigint();
  const duration = Number(end - start) / 1_000_000;
  fibComputationDurationMs.observe(duration);

  if (!res.writableEnded) {
    res.json({
      n,
      result,
      duration
    });
  }
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Fibonacci server started on port ${PORT} with pool size ${POOL_SIZE}`);
});