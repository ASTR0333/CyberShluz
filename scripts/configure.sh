#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

if [[ "${1:-}" == "--env-file" ]]; then
    [[ -n "${2:-}" ]] || { echo "--env-file requires a path" >&2; exit 2; }
    ENV_FILE="$2"
fi

if [[ ! -t 0 ]]; then
    echo "Interactive configuration requires a terminal." >&2
    exit 2
fi

read_existing() {
    local key="$1" fallback="$2" value=""
    if [[ -f "${ENV_FILE}" ]]; then
        value="$(grep -E "^${key}=" "${ENV_FILE}" | tail -1 | cut -d= -f2- || true)"
    fi
    printf '%s' "${value:-$fallback}"
}

ask() {
    local key="$1" prompt="$2" fallback="$3" value=""
    read -r -p "${prompt} [${fallback}]: " value
    printf -v "${key}" '%s' "${value:-$fallback}"
}

ask_secret() {
    local key="$1" prompt="$2" fallback="$3" value=""
    read -r -s -p "${prompt} [Enter = keep/generate]: " value
    echo
    printf -v "${key}" '%s' "${value:-$fallback}"
}

random_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32
    else
        od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
    fi
}

if [[ -f "${ENV_FILE}" ]]; then
    read -r -p "${ENV_FILE} already exists. Replace it? [y/N]: " confirm
    [[ "${confirm}" =~ ^[Yy]$ ]] || exit 0
fi

ask APP_ENV "Application environment" "$(read_existing APP_ENV production)"
ask HOST_PORT "Public HTTP port" "$(read_existing HOST_PORT 80)"
ask COMPOSE_PROJECT_NAME "Docker Compose project name" "$(read_existing COMPOSE_PROJECT_NAME cybershluz)"
ask OS_AUTH_URL "OpenStack Keystone URL" "$(read_existing OS_AUTH_URL https://edu.cyber-infrastructure.ru:5000/v3)"
ask OS_PROJECT_NAME "OpenStack project name" "$(read_existing OS_PROJECT_NAME '')"
ask OS_USERNAME "OpenStack username" "$(read_existing OS_USERNAME '')"
ask_secret OS_PASSWORD "OpenStack password" "$(read_existing OS_PASSWORD '')"
ask OS_USER_DOMAIN_NAME "OpenStack user domain" "$(read_existing OS_USER_DOMAIN_NAME Hackhaton)"
ask OS_PROJECT_DOMAIN_NAME "OpenStack project domain" "$(read_existing OS_PROJECT_DOMAIN_NAME Hackhaton)"
ask OS_REGION_NAME "OpenStack region" "$(read_existing OS_REGION_NAME RegionOne)"
ask OS_NETWORK_NAME "Default external network" "$(read_existing OS_NETWORK_NAME Public)"
ask VM_ADMIN_USER "Administrative VM user" "$(read_existing VM_ADMIN_USER labadmin)"
ask VM_STUDENT_USER "Unprivileged VM user" "$(read_existing VM_STUDENT_USER student)"
ask VM_BOOTSTRAP_USER "Legacy image initial SSH user (empty disables password bootstrap)" "$(read_existing VM_BOOTSTRAP_USER "$(read_existing VM_DEFAULT_USER '')")"
ask_secret VM_BOOTSTRAP_PASSWORD "Legacy image initial SSH password (empty disables password bootstrap)" "$(read_existing VM_BOOTSTRAP_PASSWORD "$(read_existing VM_DEFAULT_PASSWORD '')")"
ask VM_BUILD_TIMEOUT "Maximum shared VM build wait in seconds" "$(read_existing VM_BUILD_TIMEOUT 600)"
ask SSH_BOOTSTRAP_TIMEOUT "SSH bootstrap timeout in seconds" "$(read_existing SSH_BOOTSTRAP_TIMEOUT 240)"
ask DEPLOYMENT_STALE_TIMEOUT "Deployment heartbeat timeout in seconds" "$(read_existing DEPLOYMENT_STALE_TIMEOUT 1200)"
ask DEFAULT_TTL_HOURS "Stand TTL in hours" "$(read_existing DEFAULT_TTL_HOURS 2)"
ask FREEZE_DURATION_HOURS "Freeze duration in hours" "$(read_existing FREEZE_DURATION_HOURS 24)"
ask MAX_CLUSTER_UTILIZATION "Maximum projected cluster utilization (0..1)" "$(read_existing MAX_CLUSTER_UTILIZATION 0.9)"

DB_PASSWORD="$(read_existing DB_PASSWORD "$(random_secret)")"
JWT_SECRET_KEY="$(read_existing JWT_SECRET_KEY "$(random_secret)")"
MOODLE_SHARED_SECRET="$(read_existing MOODLE_SHARED_SECRET "$(random_secret)")"

for required in OS_PROJECT_NAME OS_USERNAME OS_PASSWORD; do
    [[ -n "${!required}" ]] || { echo "${required} must not be empty" >&2; exit 2; }
done

mkdir -p "$(dirname "${ENV_FILE}")"
tmp_file="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"
trap 'rm -f "${tmp_file}"' EXIT
umask 077
{
    printf 'APP_ENV=%s\n' "${APP_ENV}"
    printf 'HOST_PORT=%s\n' "${HOST_PORT}"
    printf 'COMPOSE_PROJECT_NAME=%s\n' "${COMPOSE_PROJECT_NAME}"
    printf 'DB_PASSWORD=%s\n' "${DB_PASSWORD}"
    printf 'JWT_SECRET_KEY=%s\n' "${JWT_SECRET_KEY}"
    printf 'MOODLE_SHARED_SECRET=%s\n' "${MOODLE_SHARED_SECRET}"
    printf 'OS_AUTH_URL=%s\n' "${OS_AUTH_URL}"
    printf 'OS_PROJECT_NAME=%s\n' "${OS_PROJECT_NAME}"
    printf 'OS_USERNAME=%s\n' "${OS_USERNAME}"
    printf 'OS_PASSWORD=%s\n' "${OS_PASSWORD}"
    printf 'OS_USER_DOMAIN_NAME=%s\n' "${OS_USER_DOMAIN_NAME}"
    printf 'OS_PROJECT_DOMAIN_NAME=%s\n' "${OS_PROJECT_DOMAIN_NAME}"
    printf 'OS_REGION_NAME=%s\n' "${OS_REGION_NAME}"
    printf 'OS_NETWORK_NAME=%s\n' "${OS_NETWORK_NAME}"
    printf 'VM_ADMIN_USER=%s\n' "${VM_ADMIN_USER}"
    printf 'VM_STUDENT_USER=%s\n' "${VM_STUDENT_USER}"
    printf 'VM_BOOTSTRAP_USER=%s\n' "${VM_BOOTSTRAP_USER}"
    printf 'VM_BOOTSTRAP_PASSWORD=%s\n' "${VM_BOOTSTRAP_PASSWORD}"
    printf 'VM_BUILD_TIMEOUT=%s\n' "${VM_BUILD_TIMEOUT}"
    printf 'SSH_BOOTSTRAP_TIMEOUT=%s\n' "${SSH_BOOTSTRAP_TIMEOUT}"
    printf 'DEPLOYMENT_STALE_TIMEOUT=%s\n' "${DEPLOYMENT_STALE_TIMEOUT}"
    printf 'DEFAULT_TTL_HOURS=%s\n' "${DEFAULT_TTL_HOURS}"
    printf 'FREEZE_DURATION_HOURS=%s\n' "${FREEZE_DURATION_HOURS}"
    printf 'MAX_CLUSTER_UTILIZATION=%s\n' "${MAX_CLUSTER_UTILIZATION}"
    printf 'ENABLE_MOCK_CHECKS=false\n'
    printf 'LTI_ISSUER=%s\n' "$(read_existing LTI_ISSUER '')"
    printf 'LTI_CLIENT_ID=%s\n' "$(read_existing LTI_CLIENT_ID '')"
    printf 'LTI_DEPLOYMENT_ID=%s\n' "$(read_existing LTI_DEPLOYMENT_ID 1)"
    printf 'LTI_AUTH_LOGIN_URL=%s\n' "$(read_existing LTI_AUTH_LOGIN_URL '')"
    printf 'LTI_AUTH_TOKEN_URL=%s\n' "$(read_existing LTI_AUTH_TOKEN_URL '')"
    printf 'LTI_KEYSET_URL=%s\n' "$(read_existing LTI_KEYSET_URL '')"
    printf 'LTI_FRONTEND_BASE_URL=%s\n' "$(read_existing LTI_FRONTEND_BASE_URL '')"
    printf 'LTI_PRIVATE_KEY_PATH=/app/ssh_keys/lti/tool_private.pem\n'
    printf 'LTI_KEY_ID=%s\n' "$(read_existing LTI_KEY_ID kibershluz-tool-key-1)"
    printf 'LTI_GRADE_LAB_ID=%s\n' "$(read_existing LTI_GRADE_LAB_ID 3)"
} >"${tmp_file}"

mv "${tmp_file}" "${ENV_FILE}"
trap - EXIT
chmod 600 "${ENV_FILE}"
echo "Configuration written to ${ENV_FILE} (mode 600)."
