# fibserver

A CPU-bound Express Fibonacci server that runs on Kubernetes (kind) with **Horizontal Pod Autoscaling (HPA)**, **Prometheus monitoring**, and **Grafana dashboards**.

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
- **Kubernetes manifests** (`k8s/`) — Deployment + Service + HPA + Prometheus + Ingress + Grafana.
- **metrics-server** — required sensor for HPA; kind does *not* ship it by default.
- **Prometheus** — scrapes `/metrics` from every `fibserver` pod via Kubernetes pod discovery.
- **Grafana (Helm)** — visualizes Prometheus metrics; data source and dashboard are provisioned automatically.
- **k6 load test** (`loadtest/`) — staged-ramp traffic generator, runs in-cluster as a Job.
- **Custom autoscaler** (`autoscaler.py`) — Python-based controller scaling pods dynamically based on real-time Prometheus RPS with cooldown.
- **nginx ingress** — routes external HTTP traffic into the cluster at `localhost:80`.

## Prerequisites

- [Docker](https://www.docker.com/)
- [kind](https://kind.sigs.k8s.io/) — `kind version` (tested with v0.33.0)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) — `kubectl version --client`
- [Helm](https://helm.sh/) — `helm version` (used to install Grafana)

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

### 6. Install Grafana (via Helm)

Add the Grafana Helm repo, then install Grafana with the values that provision
Prometheus as the default data source and enable the dashboard sidecar:

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install grafana grafana/grafana -f k8s/grafana-values.yaml
kubectl rollout status deploy/grafana
```

The dashboard sidecar auto-imports dashboards from ConfigMaps labelled
`grafana_dashboard: "1"`. Apply the bundled dashboard ConfigMap so Grafana shows
a pre-built **FibServer Overview** dashboard:

```bash
kubectl apply -f k8s/grafana-dashboard-cm.yaml

# after ~15s the sidecar picks it up
kubectl get configmap fibserver-dashboard
```

> The data source is provisioned in `k8s/grafana-values.yaml` under `datasources`.
> It points at `http://prometheus:9090` (the in-cluster ClusterIP Service).

### 7. Verify everything is running

```bash
kubectl get deploy,svc,hpa,ingress,pods
```

Expected state: `fibserver`, `prometheus`, `grafana`, and `ingress-nginx-controller`
all show `READY 1/1`, and the ingress `ADDRESS` is populated.

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

## Accessing Grafana

Grafana runs as a ClusterIP Service (port 80), so port-forward it to your laptop:

```bash
kubectl port-forward svc/grafana 3000:3000
```

Open `http://localhost:3000` and log in:

- **Username:** `admin`
- **Password:** `admin` (from `adminPassword` in `k8s/grafana-values.yaml`)

### What is provisioned automatically

On install, Grafana auto-configures:

1. **Data source** — a Prometheus data source pointing at `http://prometheus:9090`
   (declared in `k8s/grafana-values.yaml` → `datasources`).
2. **Dashboard** — the **FibServer Overview** dashboard, auto-imported from the
   `fibserver-dashboard` ConfigMap by the dashboard sidecar.

The dashboard includes panels for:

| Panel | PromQL |
| --- | --- |
| HTTP request rate (req/s) | `sum(rate(http_requests_total[1m])) by (route)` |
| Completed fibonacci computations/s | `sum(rate(fib_computation_duration_ms_count[1m]))` |
| Fib computation p95 latency (ms) | `histogram_quantile(0.95, sum(rate(fib_computation_duration_ms_bucket[5m])) by (le))` |
| Worker queue depth | `fib_queue_depth` |
| Node process RSS (MB) | `process_resident_memory_bytes / 1024 / 1024` |
| CPU usage (cores) | `rate(process_cpu_seconds_total[1m])` |

### Verify Grafana can reach Prometheus

With the port-forward running, query Prometheus through Grafana:

```bash
DSUID=$(curl -s -u admin:admin http://localhost:3000/api/datasources | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['uid'])")

curl -s -u admin:admin --data-urlencode 'query=up{job="fibserver"}' \
  "http://localhost:3000/api/datasources/proxy/uid/$DSUID/api/v1/query"
# → {"status":"success", ... "up" ... "1"}   (value 1 = target is up)
```

If your admin password differs from `admin`, fetch it from the secret:

```bash
kubectl get secret grafana -o jsonpath="{.data.admin-password}" | base64 --decode; echo
```

---

## Load testing with k6

The repo includes a [k6](https://k6.io/) load test that runs **inside the cluster** as a Job, so it
drives the real Service path (DNS → kube-proxy → pods) without any local installation — k6 ships
as a Docker image (`grafana/k6`).

### Why k6 (and not Locust / JMeter / wrk / hey)

| Tool | Language | Install | Distributed | Metrics story | Verdict for this project |
| --- | --- | --- | --- | --- | --- |
| **k6** | JS | single binary / Docker image | built-in (CLI or xk6-distributed) | outputs Prometheus-format metrics; same vendor as Grafana | **Best fit** |
| Locust | Python | `pip install` + web UI | master/worker fleet (web UI, heavyweight) | needs a statsd bridge to reach Prometheus | Good if you want a **web UI** and Python |
| JMeter | Java/Groovy | JRE + GUI | distributed mode | needs a backend listener | Heavy for a demo; GUI-heavy |
| wrk / hey / ab | C / Go / C | compile or brew/apt | single process only | none | fine for a quick smoke test, no scripted scenarios |

Pick **k6** for this project. Its script language is JavaScript, so it matches the Node.js
service, and it's the load generator maintained by Grafana — which pairs naturally with a
Grafana/Prometheus stack. Choose **Locust** instead only if your academic brief specifically
requires a **web-based load-test UI** or you want to write scenarios in Python.

### The test profile

`loadtest/k6-script.js` uses a **staged ramp** designed to cleanly demonstrate 100+ req/s traffic spikes and cooldown:

| Stage | Duration | Target VUs | Purpose |
| --- | --- | --- | --- |
| 1 | 20s | 2 | warm-up / baseline (~40–60 RPS, under threshold) |
| 2 | 40s | 8 | traffic spike (~150–250 RPS, triggers scale-up) |
| 3 | 60s | 1 | recovery / cooldown (~10–30 RPS for 60s, triggers 30s scale-down) |

It declares **thresholds** that make the run pass/fail rather than just "generating traffic":
error rate `< 5%` and p95 latency `< 5s`. Each request hits `/fib/15..20` (~1–5 ms per call)
allowing high request throughput, and the script records custom `fib_computations`, `fib_latency_ms`, and `fib_errors`.

### Run the test

```bash
# start watching the HPA in one terminal
kubectl get hpa fibserver -w

# run the load test (takes ~4.5 min)
kubectl apply -f loadtest/k6-job.yaml
```

Watch the HPA scale 1 → 5 under the plateau, and observe the pods:

```bash
kubectl get pods -l app=fibserver -w
kubectl top pods -l app=fibserver
```

### Read the results

```bash
# k6 prints a summary when the Job completes
kubectl logs -f job/k6-loadtest
```

Example output from a real run:

```
=== fibserver load test ===
requests:   3057
p95:        4323.5 ms
error rate: 0.00%
computations: 3057
```

Check the Job's exit status (non-zero `COMPLETIONS` means a threshold was breached):

```bash
kubectl get job k6-loadtest
```

### Watch it in Grafana

With Grafana open (`kubectl port-forward svc/grafana 3000:80`), the **FibServer Overview**
dashboard shows the whole story live as the test runs:

- **HTTP Request Rate** climbs as the ramp increases
- **Worker Queue Depth** spikes as requests outpace the 2-worker pool
- **p95 Latency** rises as the queue grows
- **CPU Usage** pins near the 500m cgroup limit, which is what the HPA is reacting to

To confirm the scale-down after the test:

```bash
kubectl describe hpa fibserver | grep SuccessfulRescale
# Normal  SuccessfulRescale  ...  New size: 5; reason: cpu ... above target
# Normal  SuccessfulRescale  ...  New size: 4; reason: All metrics below target
# Normal  SuccessfulRescale  ...  New size: 2; reason: All metrics below target
# Normal  SuccessfulRescale  ...  New size: 1; reason: All metrics below target
```

### Clean up the test

```bash
kubectl delete -f loadtest/k6-job.yaml
```

---

## Autoscaling demo (manual, without k6)

If you want a quick smoke test without the full k6 run, use the original `busybox` loadgen:

### 1. Baseline

```bash
kubectl get hpa fibserver
# NAME        REFERENCE              TARGETS       ...   REPLICAS
# fibserver   Deployment/fibserver   cpu: 2%/50%    ...   1
```

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

## Custom RPS-Based Autoscaler Demo (`autoscaler.py`)

In addition to Kubernetes' native CPU-based HPA, this repository includes [`autoscaler.py`](autoscaler.py), a custom Python autoscaling controller that polls Prometheus and scales pods dynamically based on real-time **Requests Per Second (RPS)** with a configurable cooldown period.

### How It Works

- **Sensor:** Continuously queries Prometheus via PromQL: `sum(rate(http_requests_total[30s]))`.
- **Scale-Up Condition:** When `RPS > threshold` (default `100.0 req/s`), immediately scales up the deployment by 1 replica (up to `--max 5`) and resets the cooldown timer.
- **Scale-Down Condition:** When `RPS <= threshold`, starts a 30-second cooldown timer. After 30 seconds of sustained low traffic, it scales down by 1 replica (down to `--min 1`).
- **Resilient Connectivity:** Queries Prometheus directly via HTTP (`http://localhost:9090`) or automatically falls back to in-cluster querying via `kubectl exec deploy/prometheus` (so it works even without port-forwarding running).

### Running the Custom Autoscaler Demo

#### 1. Disable native CPU HPA (Prevent controller conflict)
Since native Kubernetes HPA scales on CPU and `autoscaler.py` scales on RPS, temporarily remove the native HPA to give the script exclusive control:

```bash
kubectl delete hpa fibserver --ignore-not-found
```

*(You can re-enable the native HPA anytime with `kubectl apply -f k8s/hpa.yaml`)*.

#### 2. Start the custom autoscaler in Terminal 1
```bash
python3 autoscaler.py --threshold 100 --cooldown 30
```

Available CLI flags:
- `--threshold <req/s>`: Trigger threshold in requests/second (default: `100.0`)
- `--cooldown <seconds>`: Cooldown before scale-down (default: `30`)
- `--interval <seconds>`: Prometheus poll frequency (default: `3`)
- `--min <n>` / `--max <n>`: Pod replica bounds (default: `1` to `5`)
- `--target <deployment>`: Target Deployment name (default: `fibserver`)

#### 3. Trigger the 100+ req/s load test in Terminal 2
```bash
# Shortcut: delete previous job (if any) and launch the staged test
kubectl delete job k6-loadtest --ignore-not-found && kubectl apply -f loadtest/k6-job.yaml
```

#### 4. Observe the live scaling lifecycle
In Terminal 1, watch the colorized real-time output:

```text
[15:48:57] [STABLE]   🟢 RPS: 40.7 <= 100.0  | At minReplicas (1)
[15:49:12] [STABLE]   🟢 RPS: 74.3 <= 100.0  | At minReplicas (1)
[15:49:28] [SCALE UP] 🚀 RPS: 168.3 > 100.0  | Replicas: 1 -> 2
[15:49:30] [SCALE UP] 🚀 RPS: 168.3 > 100.0  | Replicas: 2 -> 3
[15:49:32] [SCALE UP] 🚀 RPS: 168.3 > 100.0  | Replicas: 3 -> 4
[15:49:35] [SCALE UP] 🚀 RPS: 168.3 > 100.0  | Replicas: 4 -> 5
[15:49:38] [AT MAX]   🔥 RPS: 207.1 > 100.0  | Max replicas (5) reached
...
[15:50:57] [COOLDOWN] ⏳ RPS: 8.7 <= 100.0   | Starting 30s cooldown (Replicas: 5)
[15:51:03] [COOLDOWN] ⏳ RPS: 8.7 <= 100.0   | Cooling down... 6s/30s (Replicas: 5)
[15:51:14] [COOLDOWN] ⏳ RPS: 1.7 <= 100.0   | Cooling down... 17s/30s (Replicas: 5)
[15:51:27] [SCALE DOWN] 📉 Cooldown expired (30.0s >= 30s) | Replicas: 5 -> 4
[15:51:29] [COOLDOWN]   ⏳ RPS: 1.9 <= 100.0 | Cooling down... 2s/30s (Replicas: 4)
```

#### 5. Stop the autoscaler
Press `Ctrl+C` in Terminal 1 to exit cleanly. To re-enable the native CPU-based HPA:
```bash
kubectl apply -f k8s/hpa.yaml
```

---

## Shutdown everything

```bash
# delete the k8s app resources
kubectl delete pod loadgen --force --grace-period=0   # if it is still running
kubectl delete -f loadtest/k6-job.yaml 2>/dev/null   # if the k6 Job was run
kubectl delete -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml -f k8s/prometheus.yaml -f k8s/ingress.yaml -f k8s/grafana-dashboard-cm.yaml

# uninstall Grafana (Helm)
helm uninstall grafana

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

# 5. deploy application + Prometheus + ingress
kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/hpa.yaml -f k8s/prometheus.yaml -f k8s/ingress.yaml
kubectl rollout status deploy/fibserver
kubectl rollout status deploy/prometheus

# 6. install Grafana via Helm
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update
helm install grafana grafana/grafana -f k8s/grafana-values.yaml
kubectl rollout status deploy/grafana

# 7. provision the Grafana dashboard
kubectl apply -f k8s/grafana-dashboard-cm.yaml

# 8. verify the app over the ingress
curl http://localhost:80/health
curl http://localhost:80/fib/10
```

For Prometheus (port-forward required):

```bash
kubectl port-forward svc/prometheus 9090:9090
# open http://localhost:9090
```

For Grafana (port-forward required):

```bash
kubectl port-forward svc/grafana 3000:3000
# open http://localhost:3000  (admin / admin)
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
| Grafana can't reach Prometheus ("No data" in panels) | The Prometheus service must be named `prometheus` (data source URL is `http://prometheus:9090`); check `kubectl get svc prometheus` |
| Grafana dashboard missing after install | Wait ~15s for the sidecar; ensure the `fibserver-dashboard` ConfigMap has the `grafana_dashboard: "1"` label |
| Grafana login password unknown | `kubectl get secret grafana -o jsonpath="{.data.admin-password}" \| base64 --decode` |
| k6 Job shows `Error`/`BackoffLimitExceeded` | A threshold was breached (p95 > 15s or errors > 5%), or the `fibserver` Service wasn't reachable; check `kubectl logs job/k6-loadtest` |
| k6 Job `ImagePullBackOff` | kind nodes must pull `grafana/k6` from Docker Hub; if your cluster is offline, preload with `kind load docker-image grafana/k6:0.53.0 --name kind` |
