const { parentPort } = require("worker_threads");

function fibonacci(n) {
  if (n <= 1) {
    return n;
  }

  return fibonacci(n - 1) + fibonacci(n - 2);
}

parentPort.on("message", (n) => {
  parentPort.postMessage(fibonacci(n));
});