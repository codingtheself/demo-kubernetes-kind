# fibserver

A CPU-bound Express Fibonacci server that runs on Kubernetes (kind) with **Horizontal Pod Autoscaling (HPA)** and **Prometheus monitoring**.

The server is deliberately CPU-intensive (naive recursive `fibonacci`), which makes it a great
candidate for demonstrating autoscaling. The CPU work runs in a bounded **worker-thread pool** so
that the Node.js event loop stays responsive and the pod stays healthy (readiness/liveness probes
always answer) even while the CPU is saturated.

## Architecture

```
                         ┌─────────────────────────────────────────┐
                         │              kind cluster               │
                         │                                         │
    localhost:80  ──────►│  nginx ingress ──►  Service :80         │
                         │                     ▼                   │
                         │              Pod :3000 (Express)        │
                         │                ├─ /health               │
                         │                ├─ /fib/:n (worker pool) │
                         │                └─ /metrics (prom-client)│
                         │                     ▲                   │
                         │                     │ scrapes :3000/metrics
                         │              Prometheus :9090           │
                         └─────────────────────────────────────────┘
                                      │
                              kubelet cAdvisor
                                      │
                              metrics-server ──► HPA (every 15s)
```

- **Express server** (`server.js`) — HTTP API, `/health`, `/metrics`, and a fixed-size worker pool.
- **Worker threads** (`fibWorker.js`) — heavy `fibonacci(n)` computation off the event loop.
- **Kubernetes manifests** (`k8s/`) — Deployment + Service + HPA + Prometheus + Ingress.
- **metrics-server** — required sensor for HPA; kind does *not* ship it by default.
- **Prometheus** — scrapes `/metrics` from every `fibserver` pod via Kubernetes pod discovery.
- **nginx ingress** — routes external HTTP traffic into the cluster at `localhost:80`.

## Prerequisites

- [Docker](https://www.docker.com/)
- [kind](https://kind.sigs.k8s.io/) — `kind version` (tested with v0.33.0)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) — `kubectl version --client`

## Manual setup (from scratch)

### 1. Create the kind cluster with port mappings

`kind-config.yaml` maps ports 80/443 from the kind node to your laptop so the nginx ingress
controller is reachable at `localhost:80` without port-forwarding.

```bash
kind create cluster --name kind --config kind-config.yaml
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
# NAME                 CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
# kind-control-plane   207m         10%      1168Mi          16%
```

### 3. Build the image and load it into kind

kind has no image registry, so the image is loaded into the node's Docker daemon directly.
`imagePullPolicy: IfNotPresent` in the Deployment lets the kubelet use the local copy.

```bash
docker build -t fibserver:latest .
kind load docker-image fibserver:latest --name kind
```

### 4. Install the nginx ingress controller

This must be done **before** applying the Ingress resource, otherwise the Ingress has no
controller to process it.

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller
```

### 5. Deploy the application + Prometheus + ingress

```bash
kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml -f k8s/prometheus.yaml -f k8s/ingress.yaml

kubectl rollout status deploy/fibserver
kubectl rollout status deploy/prometheus
```

### 6. Verify everything is running

```bash
kubectl get deploy,svc,hpa,ingress,pods
```

Expected state: `fibserver`, `prometheus`, and `ingress-nginx-controller` all show `READY 1/1`,
and the ingress `ADDRESS` is populated.

---

## Accessing the app

Once the ingress controller is running, the app is available at `localhost:80` — no port-forward needed.

```bash
curl http://localhost:80/health
# {"status":"ok"}

curl http://localhost:80/fib/20
# {"n":20,"result":6765,"duration":3.66}

curl http://localhost:80/metrics | head -20
# HELP process_resident_memory_bytes ...
# TYPE http_requests_total counter
# http_requests_total{route="/fib/:n",method="GET",status="200"} 1
```

## Accessing Prometheus

Prometheus needs port-forwarding because kind can't provision a cloud LoadBalancer to give it
an external IP. On a real cluster (EKS, GKE), both services get external IPs automatically.

```bash
kubectl port-forward svc/prometheus 9090:9090
```

### Web UI

Open `http://localhost:9090` in your browser. In the **Graph** tab, run any of:

```
http_requests_total
fib_queue_depth
fib_computation_duration_ms_count
rate(http_requests_total[1m])
```

### API queries (from the terminal)

```bash
# request rate over the last minute
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(http_requests_total%5B1m%5D))"

# how many fib/ requests completed so far
curl -s "http://localhost:9090/api/v1/query?query=fib_computation_duration_ms_count"

# current queue depth
curl -s "http://localhost:9090/api/v1/query?query=fib_queue_depth"
```

### Verify Prometheus targets are healthy

```bash
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool
```

Both `fibserver` and `prometheus` should report `"health": "up"`.

### Custom metrics exposed by the server

| Metric | Type | Meaning |
| --- | --- | --- |
| `http_requests_total` | Counter | Total requests, labeled by route / method / status |
| `http_request_duration_ms` | Histogram | HTTP handler latency |
| `fib_computation_duration_ms` | Histogram | Wall time of `fibonacci(n)` in the worker pool |
| `fib_queue_depth` | Gauge | Requests queued waiting for a free worker |
| `process_resident_memory_bytes` | Gauge | Node RSS (from `client.collectDefaultMetrics()`) |

---

## Autoscaling demo

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
cgroup limit). The HPA formula is:

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

---

## Shutdown everything

```bash
# delete the k8s app resources
kubectl delete pod loadgen --force --grace-period=0   # if it is still running
kubectl delete -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml -f k8s/prometheus.yaml -f k8s/ingress.yaml

# delete the ingress controller
kubectl -n ingress-nginx delete -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# delete the kind cluster
kind delete cluster --name kind
```

## Restart everything (from zero)

The same flow as the manual setup above, condensed:

```bash
# 1. create cluster
kind create cluster --name kind --config kind-config.yaml

# 2. install metrics-server
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl patch deployment metrics-server -n kube-system --type=json -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl rollout status deploy/metrics-server -n kube-system

# 3. build image and load into kind
docker build -t fibserver:latest .
kind load docker-image fibserver:latest --name kind

# 4. install nginx ingress controller FIRST (before the ingress resource)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller

# 5. deploy everything
kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml -f k8s/prometheus.yaml -f k8s/ingress.yaml
kubectl rollout status deploy/fibserver
kubectl rollout status deploy/prometheus

# 6. verify the app over the ingress
curl http://localhost:80/health
curl http://localhost:80/fib/10
```

For Prometheus (port-forward required):

```bash
kubectl port-forward svc/prometheus 9090:9090
# open http://localhost:9090
```

---

## Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `localhost:80` connection refused | nginx ingress controller not installed or still rolling out; check `kubectl -n ingress-nginx get pods` |
| `kubectl top nodes` → *Metrics API not available* | metrics-server not installed or still rolling out |
| `kubectl get hpa` → `cpu: <unknown>/50%` | metrics-server hasn't scraped yet; wait ~15–30s |
| Pods crash with `OOMKilled` / Exit 137 | Too many worker threads for the memory limit; the pool is bounded by `os.cpus().length`, keep the limit ≥ 256Mi |
| Probes fail with `connection reset` / `context deadline exceeded` | The event loop is blocked — heavy CPU work must run in a worker thread, and probes must target `/health` (not `/fib`) |
| Image `ErrImagePull` | Image wasn't loaded (`kind load docker-image`) or `imagePullPolicy` pulls from a registry instead of `IfNotPresent` |
| Prometheus shows no `fibserver` target | Deployment pod template lacks the `prometheus.io/scrape` annotations, or the pod rollout after adding them (re-`kubectl apply -f k8s/deployment.yaml`) |
| Target exists but `health: "down"` | `/metrics` not reachable — check the annotation port matches `containerPort` (3000) and the app was rebuilt with `prom-client` |
| Prometheus UI breaks at `/prometheus` path | Prometheus expects to run at the root; access it at `localhost:9090` directly, not through an Ingress path prefix |
