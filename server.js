const express = require("express");
const { Worker } = require("worker_threads");
const os = require("os");
const path = require("path");

const app = express();

const PORT = 3000;
const POOL_SIZE = Math.max(1, os.cpus().length);

const taskQueue = [];
const workers = [];

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
}

function computeFibonacci(n) {
  return new Promise((resolve, reject) => {
    taskQueue.push({ n, resolve, reject });
    processQueue();
  });
}

initPool();

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
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

  res.json({
    n,
    result,
    duration
  });
});

app.listen(PORT, "0.0.0.0", () => {
  console.log(`Fibonacci server started on port ${PORT} with pool size ${POOL_SIZE}`);
});