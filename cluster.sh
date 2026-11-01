#!/usr/bin/env bash
#
# cluster.sh - Complete Lifecycle Management for fibserver Kubernetes Cluster
#
# Usage:
#   ./cluster.sh start      - Start or initialize the Kind cluster, ingress, Prometheus & app
#   ./cluster.sh stop       - Pause/stop the cluster containers (fast, preserves state)
#   ./cluster.sh destroy    - Completely delete the Kind cluster and all resources
#   ./cluster.sh restart    - Restart the cluster and verify endpoints
#   ./cluster.sh status     - Show status of all cluster nodes, pods, services, and health
#   ./cluster.sh test       - Run the in-cluster k6 generalization load test
#

set -e

# Always force docker provider for kind
export KIND_EXPERIMENTAL_PROVIDER=docker

# ANSI Color Codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

CLUSTER_NAME="kind"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log_info()    { echo -e "${CYAN}${BOLD}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}${BOLD}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}${BOLD}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}${BOLD}[ERROR]${NC} $1"; }

check_prereqs() {
    log_info "Checking prerequisites (docker, kind, kubectl, helm)..."
    for tool in docker kind kubectl helm; do
        if ! command -v "$tool" &>/dev/null; then
            log_error "Missing required tool: $tool. Please install it first."
            exit 1
        fi
    done
    if ! docker info &>/dev/null; then
        log_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
}

start_cluster() {
    check_prereqs

    # 1. Check if kind cluster container already exists
    if docker ps -a --format '{{.Names}}' | grep -q "^${CLUSTER_NAME}-control-plane$"; then
        if docker ps --format '{{.Names}}' | grep -q "^${CLUSTER_NAME}-control-plane$"; then
            log_info "Kind cluster container '${CLUSTER_NAME}-control-plane' is already running."
        else
            log_info "Waking up existing Kind container '${CLUSTER_NAME}-control-plane'..."
            docker start "${CLUSTER_NAME}-control-plane"
        fi
    else
        log_info "Creating fresh Kind cluster using kind-config.yaml..."
        kind create cluster --name "$CLUSTER_NAME" --config kind-config.yaml
    fi

    # 2. Wait for Kubernetes API server
    log_info "Waiting for Kubernetes API server to respond..."
    until kubectl cluster-info &>/dev/null; do
        sleep 2
    done
    kubectl wait --for=condition=Ready nodes --all --timeout=60s

    # 3. Build & load fibserver docker image
    log_info "Building fibserver:latest Docker image..."
    docker build -t fibserver:latest . -q
    log_info "Loading image into Kind node daemon..."
    kind load docker-image fibserver:latest --name "$CLUSTER_NAME"

    # 4. Install / Verify metrics-server (required for metrics API & top)
    if ! kubectl get deployment metrics-server -n kube-system &>/dev/null; then
        log_info "Installing metrics-server with insecure TLS patch for Kind..."
        kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
        kubectl patch deployment metrics-server -n kube-system --type=json \
            -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
    fi

    # 5. Install / Verify ingress-nginx controller
    if ! kubectl get namespace ingress-nginx &>/dev/null; then
        log_info "Installing Ingress NGINX controller..."
        kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
    fi
    log_info "Waiting for Ingress NGINX controller to become ready..."
    kubectl -n ingress-nginx rollout status deploy/ingress-nginx-controller --timeout=90s

    # 6. Apply application manifests
    log_info "Deploying fibserver, Prometheus, and Ingress..."
    kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml -f k8s/prometheus.yaml -f k8s/ingress.yaml
    kubectl rollout status deploy/fibserver --timeout=60s
    kubectl rollout status deploy/prometheus --timeout=60s

    # 7. Grafana (Helm)
    if ! helm status grafana &>/dev/null; then
        log_info "Installing Grafana via Helm..."
        helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
        helm repo update grafana 2>/dev/null || true
        helm install grafana grafana/grafana -f k8s/grafana-values.yaml
    fi
    kubectl apply -f k8s/grafana-dashboard-cm.yaml

    # 8. Verification & smoke test
    log_info "Verifying endpoints via NGINX ingress at http://localhost:80..."
    sleep 3
    local retries=10
    local success=false
    while [ $retries -gt 0 ]; do
        if curl -sf http://localhost:80/health &>/dev/null; then
            success=true
            break
        fi
        sleep 2
        retries=$((retries - 1))
    done

    if [ "$success" = true ]; then
        log_success "All cluster components are active and healthy!"
        echo ""
        echo -e "${GREEN}  ✓ fibserver API     : http://localhost:80/health${NC}"
        echo -e "${GREEN}  ✓ Fibonacci Demo    : http://localhost:80/fib/15${NC}"
        echo -e "${GREEN}  ✓ Prometheus Target : kubectl port-forward svc/prometheus 9090:9090${NC}"
        echo -e "${GREEN}  ✓ Grafana Dashboard : kubectl port-forward svc/grafana 3000:3000 (admin / admin)${NC}"
        echo ""
        echo -e "${BOLD}${CYAN}To launch the AI Predictive Autoscaler:${NC}"
        echo -e "  ${BOLD}./predictive_autoscaler.py --pod-capacity 50.0 --cooldown 45${NC}"
        echo ""
        echo -e "${BOLD}${CYAN}To run the k6 load test:${NC}"
        echo -e "  ${BOLD}./cluster.sh test${NC}"
        echo ""
    else
        log_warn "Ingress is still warming up. Run './cluster.sh status' in a few seconds to verify."
    fi
}

stop_cluster() {
    log_info "Pausing Kind cluster containers (preserving state)..."
    if docker ps --format '{{.Names}}' | grep -q "^${CLUSTER_NAME}-control-plane$"; then
        docker stop "${CLUSTER_NAME}-control-plane"
        log_success "Cluster stopped cleanly. Run './cluster.sh start' to wake it back up."
    else
        log_info "Cluster is already stopped."
    fi
}

destroy_cluster() {
    log_warn "Completely destroying Kind cluster '${CLUSTER_NAME}'..."
    kind delete cluster --name "$CLUSTER_NAME" 2>/dev/null || true
    log_success "Cluster destroyed."
}

show_status() {
    check_prereqs
    echo ""
    echo -e "${BOLD}${CYAN}=== Kubernetes Cluster Status ===${NC}"
    if ! docker ps --format '{{.Names}}' | grep -q "^${CLUSTER_NAME}-control-plane$"; then
        log_warn "Kind cluster container is NOT running. Run './cluster.sh start' first."
        return
    fi

    kubectl get nodes
    echo ""
    echo -e "${BOLD}${CYAN}=== Pods in 'default' and 'ingress-nginx' ===${NC}"
    kubectl get pods -n default
    kubectl get pods -n ingress-nginx
    echo ""
    echo -e "${BOLD}${CYAN}=== Ingress Endpoints ===${NC}"
    kubectl get ingress
    echo ""
    echo -e "${BOLD}${CYAN}=== Smoke Test Response ===${NC}"
    curl -s http://localhost:80/health || echo "Endpoint unreachable"
    echo ""
    curl -s http://localhost:80/fib/10 || echo "Endpoint unreachable"
    echo ""
}

run_k6_test() {
    log_info "Triggering in-cluster k6 generalization test job..."
    kubectl delete job k6-generalization 2>/dev/null || true
    kubectl delete configmap k6-generalization-script 2>/dev/null || true
    kubectl apply -f loadtest/k6-generalization-job.yaml
    log_info "Waiting for k6 container to initialize..."
    local retries=30
    while [ $retries -gt 0 ]; do
        local phase
        phase=$(kubectl get pod -l app=k6-generalization -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)
        if [ "$phase" = "Running" ] || [ "$phase" = "Succeeded" ]; then
            break
        fi
        sleep 1
        retries=$((retries - 1))
    done
    log_info "Job running! Streaming live k6 telemetry logs..."
    kubectl logs -f job/k6-generalization
}

open_grafana() {
    log_info "Starting port-forward for Grafana..."
    echo ""
    echo -e "${GREEN}${BOLD}===================================================================${NC}"
    echo -e "${GREEN}${BOLD}  Grafana Web UI : ${CYAN}http://localhost:3000${NC}"
    echo -e "${GREEN}${BOLD}  Username       : ${YELLOW}admin${NC}"
    echo -e "${GREEN}${BOLD}  Password       : ${YELLOW}admin${NC}"
    echo -e "${GREEN}${BOLD}===================================================================${NC}"
    echo -e "Press ${BOLD}Ctrl+C${NC} anytime to stop the port-forward."
    echo ""
    kubectl port-forward svc/grafana 3000:80
}

open_prometheus() {
    log_info "Starting port-forward for Prometheus..."
    echo ""
    echo -e "${GREEN}${BOLD}===================================================================${NC}"
    echo -e "${GREEN}${BOLD}  Prometheus Web UI : ${CYAN}http://localhost:9090${NC}"
    echo -e "${GREEN}${BOLD}===================================================================${NC}"
    echo -e "Press ${BOLD}Ctrl+C${NC} anytime to stop the port-forward."
    echo ""
    kubectl port-forward svc/prometheus 9090:9090
}

case "$1" in
    start|up)
        start_cluster
        ;;
    stop|down)
        stop_cluster
        ;;
    destroy)
        destroy_cluster
        ;;
    restart)
        stop_cluster
        sleep 2
        start_cluster
        ;;
    status)
        show_status
        ;;
    test)
        run_k6_test
        ;;
    traffic)
        python3 traffic.py --rps "${2:-120}"
        ;;
    monitor)
        python3 monitor.py
        ;;
    grafana|dashboard)
        open_grafana
        ;;
    prometheus)
        open_prometheus
        ;;
    *)
        echo "Usage: $0 {start|stop|destroy|restart|status|test|traffic [RPS]|monitor|grafana|prometheus}"
        exit 1
        ;;
esac
