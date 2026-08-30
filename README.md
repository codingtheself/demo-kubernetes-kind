# fibserver

A CPU-bound Express Fibonacci server that runs on Kubernetes (kind) with **Horizontal Pod Autoscaling (HPA)**.

The server is deliberately CPU-intensive (naive recursive `fibonacci`), which makes it a great
candidate for demonstrating autoscaling. The CPU work runs in a bounded **worker-thread pool** so
that the Node.js event loop stays responsive and the pod stays healthy (readiness/liveness probes
always answer) even while the CPU is saturated.

## Architecture

- **Express server** (`server.js`) — HTTP API, health endpoint, and a fixed-size worker pool.
- **Worker threads** (`fibWorker.js`) — heavy `fibonacci(n)` computation off the event loop.
- **Kubernetes manifests** (`k8s/`) — Deployment + Service + HPA (autoscaling/v2).
- **metrics-server** — required sensor for HPA; kind does *not* ship it by default.

```
client → Service :80  →  Pod :3000 (Express / worker pool)         [loadgen pod in cluster]
                           ▲
                           │  CPU usage via kubelet (cAdvisor) every ~1s
                      metrics-server scrapes every 15s
                           │
                           ▼
                      metrics.k8s.io API  →  HPA (every 15s)  →  changes Deployment replicas
```

## Prerequisites

- [Docker](https://www.docker.com/)
- [kind](https://kind.sigs.k8s.io/) — `kind version` (tested with v0.33.0)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) — `kubectl version --client`

## Setup

### 1. Create the kind cluster

```bash
kind create cluster --name kind
kubectl cluster-info
```

### 2. Install metrics-server (required for HPA)

Without it, `kubectl top` fails with *"Metrics API not available"* and the HPA reports
`cpu: <unknown>`.

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# kind uses self-signed kubelet certs, so metrics-server must skip TLS verification:
kubectl patch deployment metrics-server -n kube-system --type=json -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'

kubectl rollout status deploy/metrics-server -n kube-system
```

Verify the sensor is online:

```bash
kubectl top nodes
```

### 3. Build the image and load it into kind

kind has no image registry, so the image is loaded into the node's Docker daemon directly.
`imagePullPolicy: IfNotPresent` in the Deployment lets the kubelet use the local copy.

```bash
docker build -t fibserver:latest .
kind load docker-image fibserver:latest --name kind
```

### 4. Deploy the application

```bash
kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml
kubectl rollout status deploy/fibserver
```

Expected state:

```bash
kubectl get deploy,svc,hpa,pods
```

## Verify the API works

Port-forward the Service and hit the endpoints:

```bash
kubectl port-forward svc/fibserver 3000:80
```

In another terminal:

```bash
curl http://localhost:3000/health
# {"status":"ok"}

curl http://localhost:3000/fib/35
# {"n":35,"result":9227465,"duration":266.9}
```

`/fib/:n` returns `n`, the Fibonacci value, and how long it took in ms. Use `-w` to see status codes:

```bash
curl -w "\nHTTP %{http_code}\n" http://localhost:3000/fib/5
# {"n":5,"result":5,"duration":...}
# HTTP 200

curl -w "\nHTTP %{http_code}\n" http://localhost:3000/fib/-1
# {"n":...} HTTP 400 (invalid input)
```

## Verify autoscaling

### 1. Baseline

```bash
kubectl get hpa fibserver
# NAME        REFERENCE              TARGETS       ...   REPLICAS
# fibserver   Deployment/fibserver   cpu: 2%/50%    ...   1
```

At idle there is 1 replica running at a few percent of the 50m CPU request.

### 2. Apply load

Create a `loadgen` pod **inside the cluster** (it hits the real Service path: DNS → kube-proxy → pods).
It launches 14 parallel `while true` loops, each firing a CPU-heavy `fib/42` request:

```bash
kubectl run loadgen --image=busybox --restart=Never --overrides='{"spec":{"containers":[{"name":"loadgen","image":"busybox","command":["/bin/sh","-c","for i in $(seq 1 14); do (while true; do wget -q -O /dev/null http://fibserver/fib/42; done) & done; wait"],"resources":{"requests":{"cpu":"100m"}}}]}}'
```

Watch the HPA scale up (1 → 2 → 4 → 5, a bit after metrics-server starts reporting):

```bash
kubectl get hpa fibserver -w
```

The important column is `TARGETS`. Under load it will peg at something like
`cpu: 1000%/50%` — meaning pods are using ~1000% of their 50m request (capped by the 500m
cgroup limit). The HPA formula is additively simple:

```
desiredReplicas = ceil( currentReplicas × currentUtilization / targetUtilization )
```

Confirm CPU saturation and healthy pods:

```bash
kubectl top pods -l app=fibserver
kubectl get pods -l app=fibserver
```

All pods should be `1/1 Running` (the `/health` probes keep passing because the worker pool
keeps the event loop responsive).

### 3. Watch it scale back down

Delete the load generator:

```bash
kubectl delete pod loadgen
```

CPU drains quickly; the HPA waits its scale-down **stabilization window** (set to 30s here via
`behavior.scaleDown.stabilizationWindowSeconds`) and then returns to `minReplicas: 1`:

```bash
kubectl get hpa fibserver -w
# ... REPLICAS goes 5 → 1 after ~30s of low utilization
```

### Cleanup

```bash
kubectl delete pod loadgen --force --grace-period=0   # if still running
kubectl delete -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml
kind delete cluster --name kind
```

## Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `kubectl top nodes` → *Metrics API not available* | metrics-server not installed or still rolling out |
| `kubectl get hpa` → `cpu: <unknown>/50%` | metrics-server hasn't scraped yet; wait ~15–30s |
| Pods crash with `OOMKilled` / Exit 137 | Too many worker threads for the memory limit; the pool is bounded by `os.cpus().length`, keep the limit ≥ 256Mi |
| Probes fail with `connection reset` / `context deadline exceeded` | The event loop is blocked — heavy CPU work must run in a worker thread, and probes must target `/health` (not `/fib`) |
| Image `ErrImagePull` | Image wasn't loaded (`kind load docker-image`) or `imagePullPolicy` pulls from a registry instead of `IfNotPresent` |
