#!/bin/bash

# Thank you Claude for this fancy script!
# ═══════════════════════════════════════════════════════════════════════════════
#  🐘 PostgreSQL Integration Test Environment Setup
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

# Configuration
CRUNCHY_DATA_OPERATOR_VERSION="5.8.2"
CLUSTER_NAME="postgres-test"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFESTS_DIR="${SCRIPT_DIR}/manifests"

# Colors and formatting
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly PURPLE='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly WHITE='\033[1;37m'
readonly NC='\033[0m' # No Color
readonly BOLD='\033[1m'

# Emoji indicators
readonly CHECK="✅"
readonly CROSS="❌"
readonly ROCKET="🚀"
readonly CLOCK="⏳"
readonly ELEPHANT="🐘"
readonly GEAR="⚙️"

# Logging functions
log_info() {
  echo -e "${BLUE}${BOLD}ℹ️  INFO:${NC} $1"
}

log_success() {
  echo -e "${GREEN}${BOLD}${CHECK} SUCCESS:${NC} $1"
}

log_warning() {
  echo -e "${YELLOW}${BOLD}⚠️  WARNING:${NC} $1"
}

log_error() {
  echo -e "${RED}${BOLD}${CROSS} ERROR:${NC} $1" >&2
}

log_step() {
  echo -e "\n${PURPLE}${BOLD}${GEAR} STEP $1:${NC} $2"
}

show_banner() {
  echo -e "${CYAN}${BOLD}"
  cat <<'EOF'
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║        🐘 PostgreSQL Integration Test Environment            ║
    ║                                                               ║
    ║        Powered by Kind + Crunchy Data Operator               ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
EOF
  echo -e "${NC}"
}

# Cleanup function
cleanup() {
  if [[ "${1:-}" == "EXIT" ]]; then
    log_warning "Script interrupted. Cleaning up..."
    kind delete cluster --name="${CLUSTER_NAME}" 2>/dev/null || true
    exit 1
  fi
}

# Validation functions
check_prerequisites() {
  log_step "1" "Checking prerequisites"

  local missing_tools=()

  command -v kind >/dev/null 2>&1 || missing_tools+=("kind")
  command -v kubectl >/dev/null 2>&1 || missing_tools+=("kubectl")
  command -v helm >/dev/null 2>&1 || missing_tools+=("helm")

  if [[ ${#missing_tools[@]} -ne 0 ]]; then
    log_error "Missing required tools: ${missing_tools[*]}"
    log_info "Please install the missing tools and try again"
    exit 1
  fi

  if [[ ! -f "${MANIFESTS_DIR}/kind-cluster-config.yaml" ]]; then
    log_error "Kind cluster config not found at: ${MANIFESTS_DIR}/kind-cluster-config.yaml"
    exit 1
  fi

  if [[ ! -f "${MANIFESTS_DIR}/pg-cluster.yaml" ]]; then
    log_error "PostgreSQL operator manifest not found at: ${MANIFESTS_DIR}/pg-cluster.yaml"
    exit 1
  fi

  log_success "All prerequisites satisfied"
}

# Progress indicator
show_progress() {
  local duration=$1
  local sleep_interval=0.1
  local progress=0
  local bar_length=50

  echo -ne "${CLOCK} "
  while [[ $progress -lt $duration ]]; do
    local percentage=$((progress * 100 / duration))
    local filled_length=$((percentage * bar_length / 100))
    local bar=$(printf "%*s" $filled_length | tr ' ' '█')
    local empty=$(printf "%*s" $((bar_length - filled_length)) | tr ' ' '░')

    echo -ne "\r${CLOCK} Progress: [${GREEN}${bar}${NC}${empty}] ${percentage}%"
    sleep $sleep_interval
    progress=$((progress + 1))
  done
  echo -e "\n"
}

# Deployment functions
create_kind_cluster() {
  log_step "2" "Creating Kind cluster '${CLUSTER_NAME}'"

  # Check if cluster already exists
  if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    log_warning "Cluster '${CLUSTER_NAME}' already exists"
    read -p "Delete existing cluster and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      log_info "Deleting existing cluster..."
      kind delete cluster --name="${CLUSTER_NAME}"
    else
      log_info "Using existing cluster"
      return 0
    fi
  fi

  log_info "Creating cluster with config: ${MANIFESTS_DIR}/kind-cluster-config.yaml"
  if kind create cluster --name="${CLUSTER_NAME}" --config="${MANIFESTS_DIR}/kind-cluster-config.yaml"; then
    log_success "Kind cluster '${CLUSTER_NAME}' created successfully"
  else
    log_error "Failed to create Kind cluster"
    exit 1
  fi
}

install_crunchy_operator() {
  log_step "3" "Installing Crunchy Data Operator v${CRUNCHY_DATA_OPERATOR_VERSION}"

  log_info "Adding Crunchy Data Helm repository..."

  if helm install pgo \
    --namespace pgo \
    --create-namespace \
    --version "${CRUNCHY_DATA_OPERATOR_VERSION}" \
    --wait \
    --timeout=300s \
    oci://registry.developers.crunchydata.com/crunchydata/pgo; then
    log_success "Crunchy Data Operator installed successfully"
  else
    log_error "Failed to install Crunchy Data Operator"
    exit 1
  fi
}

setup_postgres_namespace() {
  log_step "4" "Setting up PostgreSQL namespace"

  if kubectl create namespace postgres --dry-run=client -o yaml | kubectl apply -f -; then
    log_success "PostgreSQL namespace ready"
  else
    log_error "Failed to create PostgreSQL namespace"
    exit 1
  fi
}

deploy_postgres_cluster() {
  log_step "5" "Deploying PostgreSQL cluster"

  log_info "Applying PostgreSQL cluster manifest..."
  if kubectl apply -f "${MANIFESTS_DIR}/pg-cluster.yaml"; then
    log_success "PostgreSQL cluster deployment initiated"
  else
    log_error "Failed to deploy PostgreSQL cluster"
    exit 1
  fi
}

wait_for_cluster_ready() {
  log_step "6" "Waiting for PostgreSQL cluster to be ready"

  log_info "This may take a few minutes..."

  local timeout=300
  local elapsed=0
  local sleep_interval=5

  while [[ $elapsed -lt $timeout ]]; do
    # Check if all containers in PostgreSQL pods are ready
    local pods_ready=true
    local pod_names

    # Get all pods in postgres namespace
    pod_names=$(kubectl get pods -n postgres -o name 2>/dev/null | grep -v NAME || echo "")

    if [[ -n "$pod_names" ]]; then
      while IFS= read -r pod; do
        if [[ -n "$pod" ]]; then
          # Check if all containers in this pod are ready
          local container_statuses
          container_statuses=$(kubectl get "$pod" -n postgres -o jsonpath='{.status.containerStatuses[*].ready}' 2>/dev/null || echo "")

          if [[ -n "$container_statuses" ]]; then
            # Check if any container is not ready (contains "false")
            if echo "$container_statuses" | grep -q "false"; then
              pods_ready=false
              break
            fi
          else
            pods_ready=false
            break
          fi
        fi
      done <<<"$pod_names"
    else
      pods_ready=false
    fi

    if [[ "$pods_ready" == "true" ]]; then
      log_success "All PostgreSQL containers are ready!"
      return 0
    fi

    echo -ne "\r${CLOCK} Waiting for containers to be ready... (${elapsed}s/${timeout}s)"
    sleep $sleep_interval
    elapsed=$((elapsed + sleep_interval))
  done

  echo
  log_warning "Containers not ready within timeout, but deployment may still be in progress"
  log_info "Check status with: kubectl get pods -n postgres"
}

show_cluster_info() {
  log_step "7" "Cluster Information"

  echo -e "${WHITE}${BOLD}📊 Cluster Status:${NC}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  echo -e "${CYAN}🎯 Cluster Name:${NC} ${CLUSTER_NAME}"
  echo -e "${CYAN}🔧 Operator Version:${NC} ${CRUNCHY_DATA_OPERATOR_VERSION}"
  echo -e "${CYAN}🌐 Cluster Context:${NC} kind-${CLUSTER_NAME}"

  echo -e "\n${WHITE}${BOLD}🔍 Quick Commands:${NC}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo -e "${YELLOW}# Check PostgreSQL clusters:${NC}"
  echo "  kubectl get postgresclusters -n postgres"
  echo
  echo -e "${YELLOW}# Check operator status:${NC}"
  echo "  kubectl get pods -n pgo"
  echo
  # echo -e "${YELLOW}# Port forward to PostgreSQL:${NC}"
  # echo "  kubectl port-forward -n postgres svc/<cluster-name>-primary 5432:5432"
  # echo
  echo -e "${YELLOW}# Clean up:${NC}"
  echo "  kind delete cluster --name=${CLUSTER_NAME}"

  echo -e "\n${GREEN}${BOLD}${ROCKET} Deployment completed successfully!${NC}"
}

# Main execution
main() {
  # Set up signal handlers
  trap 'cleanup EXIT' INT TERM

  show_banner

  check_prerequisites
  create_kind_cluster
  install_crunchy_operator
  setup_postgres_namespace
  deploy_postgres_cluster
  wait_for_cluster_ready
  show_cluster_info

  echo -e "\n${ELEPHANT} Happy testing! ${ELEPHANT}"
}

# Show help
show_help() {
  cat <<EOF
Usage: $0 [OPTIONS]

Options:
    -h, --help              Show this help message
    -c, --clean             Clean up existing cluster before deploying
    -c, --destroy           Destroy existing cluster and exit
    -v, --version VERSION   Set Crunchy Data Operator version (default: ${CRUNCHY_DATA_OPERATOR_VERSION})

Examples:
    $0                      Deploy with default settings
    $0 --clean              Clean existing cluster and deploy fresh
    $0 --version 5.8.1      Deploy with specific operator version

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h | --help)
      show_help
      exit 0
      ;;
    -c | --clean)
      log_info "Cleaning up existing cluster..."
      kind delete cluster --name="${CLUSTER_NAME}" 2>/dev/null || true
      shift
      ;;
    -d | --destroy)
      log_info "Destroying existing cluster and exiting..."
      kind delete cluster --name="${CLUSTER_NAME}" 2>/dev/null || true
      exit 0
      ;;
    -v | --version)
      CRUNCHY_DATA_OPERATOR_VERSION="$2"
      shift 2
      ;;
    *)
      log_error "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

# Run main function
main "$@"
