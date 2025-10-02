#!/usr/bin/env bash
set -euo pipefail
# Usage: docker_launch.sh IMAGE CONTAINER_NAME RDP_PORT CPU_LIMIT MEMORY_LIMIT_MB GPU_FLAG USERNAME PASSWORD

IMAGE="${1:-}"
CNAME="${2:-}"
RDP_PORT="${3:-}"
CPU_LIMIT="${4:-}"
MEM_LIMIT_MB="${5:-}"
GPU_FLAG="${6:-false}"
USR="${7:-}"
PWD="${8:-}"

if [[ -z "$IMAGE" || -z "$CNAME" || -z "$RDP_PORT" || -z "$CPU_LIMIT" || -z "$MEM_LIMIT_MB" ]]; then
  echo "Paramètre manquant" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker introuvable" >&2
  exit 1
fi

if ss -ltn | awk '{print $4}' | grep -q ":$RDP_PORT$"; then
  echo "Port $RDP_PORT déjà utilisé" >&2
  exit 2
fi

# Pull auto si image absente (plus de liste blanche)
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker pull "$IMAGE" >/dev/null
fi

GPU_ARGS=()
if [[ "$GPU_FLAG" == "true" ]]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    GPU_ARGS+=(--gpus 1)
  fi
fi

MEM_DOCKER="${MEM_LIMIT_MB}m"

set +e
CID=$(docker run -d \
  --name "$CNAME" \
  --label "managed_by=rdp_agent" \
  --label "agent_id=${AGENT_ID:-unknown}" \
  --cpus "$CPU_LIMIT" \
  --memory "$MEM_DOCKER" \
  -p "${RDP_PORT}:3389" \
  -e RDP_USER="$USR" \
  -e RDP_PASSWORD="$PWD" \
  "${GPU_ARGS[@]}" \
  "$IMAGE" 2>&1)
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "$CID" >&2
  exit $RC
fi

echo "$CID"