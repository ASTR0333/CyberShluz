#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

DOCKER_CMD=(docker)

ENV_FILE="${ENV_FILE:-.env}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"
ACTION="up"
REBUILD=0
SHOW_LOGS=0
PULL=0

as_root() {
    if [[ "${EUID}" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        echo "This operation requires root privileges and sudo is not installed." >&2
        return 1
    fi
}

require_ubuntu_2404() {
    [[ -r /etc/os-release ]] || {
        echo "Automatic Docker installation is supported only on Ubuntu Server 24.04." >&2
        return 1
    }

    # shellcheck disable=SC1091
    source /etc/os-release
    if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
        echo "Automatic Docker installation is supported only on Ubuntu Server 24.04; detected ${PRETTY_NAME:-unknown OS}." >&2
        echo "Install Docker Engine and Docker Compose v2 manually, then run this script again." >&2
        return 1
    fi
}

install_docker() {
    require_ubuntu_2404
    echo "Docker is not installed. Installing docker.io and Docker Compose v2 from Ubuntu 24.04 repositories..."
    as_root apt-get update
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2
    as_root systemctl enable --now docker
}

install_compose_plugin() {
    require_ubuntu_2404
    echo "Docker Compose v2 is missing. Installing a package compatible with the existing Docker Engine..."
    as_root apt-get update
    if dpkg-query -W -f='${Status}' docker-ce 2>/dev/null | grep -q 'install ok installed'; then
        as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-plugin
    else
        as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y docker-compose-v2
    fi
}

prepare_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        install_docker
    fi

    if ! docker compose version >/dev/null 2>&1; then
        install_compose_plugin
    fi
    docker compose version >/dev/null 2>&1 || {
        echo "Docker Compose v2 installation failed." >&2
        return 1
    }

    if docker info >/dev/null 2>&1; then
        DOCKER_CMD=(docker)
        return
    fi

    if ! as_root docker info >/dev/null 2>&1 && command -v systemctl >/dev/null 2>&1; then
        as_root systemctl enable --now docker
    fi

    if ! as_root docker info >/dev/null 2>&1; then
        echo "Docker is installed, but the daemon is unavailable." >&2
        command -v systemctl >/dev/null 2>&1 && as_root systemctl status docker --no-pager || true
        return 1
    fi

    if [[ "${EUID}" -eq 0 ]]; then
        DOCKER_CMD=(docker)
        return
    fi

    local deploy_user
    deploy_user="$(id -un)"
    as_root usermod -aG docker "${deploy_user}"
    echo "User ${deploy_user} was added to the docker group. The change becomes permanent after re-login."
    echo "This deployment will continue through sudo docker."
    DOCKER_CMD=(sudo docker)
}

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

prepare_docker

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
    "${DOCKER_CMD[@]}" compose --env-file "${ENV_FILE}" --project-name "${PROJECT_NAME}" "$@"
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
    echo "Rebuilding all application images and refreshing base images..."
    compose build --pull --no-cache
else
    # The frontend is compiled inside Docker, so the host Node.js version is
    # irrelevant. Always refresh node:lts-alpine before building to avoid
    # silently reusing an EOL Node.js layer from the local Docker cache.
    echo "Refreshing the frontend builder to the latest Node.js LTS image..."
    compose build --pull frontend
fi

compose up -d --build --remove-orphans

# Re-read Docker DNS after application containers have been replaced. This is
# also required once when upgrading from the old bind-mounted proxy config.
compose restart nginx-proxy

for attempt in $(seq 1 30); do
    if compose exec -T nginx-proxy wget -q -O /dev/null http://127.0.0.1/health >/dev/null 2>&1 &&
       compose exec -T nginx-proxy wget -q -O /dev/null http://127.0.0.1/ >/dev/null 2>&1; then
        host_port="$(grep -E '^HOST_PORT=' "${ENV_FILE}" | tail -1 | cut -d= -f2- || true)"
        echo "Deployment is healthy: http://localhost:${host_port:-80}/"
        [[ "${SHOW_LOGS}" -eq 1 ]] && compose logs --tail=200
        exit 0
    fi
    sleep 2
done

compose ps
compose logs --tail=150 backend frontend celery_worker nginx-proxy
echo "Application did not become healthy through nginx-proxy within 60 seconds." >&2
exit 1
