#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

ENV_FILE="${ENV_FILE:-.env}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"
ACTION="up"
REBUILD=0
SHOW_LOGS=0
PULL=0

usage() {
    cat <<'EOF'
Usage: ./scripts/deploy.sh [options]
  --env-file PATH       Compose environment file (default: .env)
  --project-name NAME   Isolated Compose project name (default: cybershluz)
  --configure           Run the interactive environment configurator first
  --rebuild             Rebuild without Docker layer cache
  --pull                Pull base/service images before build
  --logs                Print recent service logs after deployment
  --down                Stop the stack (persistent volumes are preserved)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --env-file) ENV_FILE="${2:?missing path}"; shift 2 ;;
        --project-name) PROJECT_NAME="${2:?missing name}"; shift 2 ;;
        --configure) bash "${REPO_ROOT}/scripts/configure.sh" --env-file "${ENV_FILE}"; shift ;;
        --rebuild) REBUILD=1; shift ;;
        --pull) PULL=1; shift ;;
        --logs) SHOW_LOGS=1; shift ;;
        --down) ACTION="down"; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
done

command -v docker >/dev/null 2>&1 || { echo "docker is not installed" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon is unavailable" >&2; exit 1; }

[[ -f "${ENV_FILE}" ]] || {
    echo "${ENV_FILE} does not exist. Run ./scripts/configure.sh --env-file ${ENV_FILE}" >&2
    exit 1
}
if [[ -z "${PROJECT_NAME}" ]]; then
    PROJECT_NAME="$(grep -E '^COMPOSE_PROJECT_NAME=' "${ENV_FILE}" | tail -1 | cut -d= -f2- || true)"
    PROJECT_NAME="${PROJECT_NAME:-cybershluz}"
fi
export APP_ENV_FILE="${ENV_FILE}"

compose() {
    docker compose --env-file "${ENV_FILE}" --project-name "${PROJECT_NAME}" "$@"
}

compose config --quiet
mkdir -p ssh_keys
if [[ "$(stat -c '%u' ssh_keys 2>/dev/null || echo 0)" != "1000" ]]; then
    if [[ "${EUID}" -eq 0 ]]; then
        chown -R 1000:1000 ssh_keys
    elif command -v sudo >/dev/null 2>&1; then
        sudo chown -R 1000:1000 ssh_keys
    else
        echo "ssh_keys must be writable by container UID 1000" >&2
        exit 1
    fi
fi
chmod 700 ssh_keys

if [[ "${ACTION}" == "down" ]]; then
    compose down
    echo "Stack ${PROJECT_NAME} stopped; volumes preserved."
    exit 0
fi

if [[ "${PULL}" -eq 1 ]]; then
    compose pull --ignore-buildable
fi
if [[ "${REBUILD}" -eq 1 ]]; then
    compose build --no-cache
fi

compose up -d --build --remove-orphans

for attempt in $(seq 1 30); do
    if compose exec -T backend curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        host_port="$(grep -E '^HOST_PORT=' "${ENV_FILE}" | tail -1 | cut -d= -f2-)"
        echo "Deployment is healthy: http://localhost:${host_port:-80}/"
        [[ "${SHOW_LOGS}" -eq 1 ]] && compose logs --tail=200
        exit 0
    fi
    sleep 2
done

compose ps
compose logs --tail=150 backend celery_worker nginx-proxy
echo "Backend did not become healthy within 60 seconds." >&2
exit 1
