#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_ID="${1:?release id is required}"
DEPLOY_ROOT="${2:?deploy root is required}"
ARCHIVE_NAME="${3:?archive name is required}"
PROJECT_NAME="${4:?Compose project name is required}"

[[ "${RELEASE_ID}" =~ ^[0-9a-f]{40}-[0-9]+-[0-9]+$ ]] || {
    echo "Invalid release id" >&2
    exit 2
}
[[ "${DEPLOY_ROOT}" == "/home/mvp_admin/cybershluz-deploy" ]] || {
    echo "Refusing to deploy outside the configured root" >&2
    exit 2
}
[[ "${ARCHIVE_NAME}" == "cybershluz-${RELEASE_ID}.tar.gz" ]] || exit 2
[[ "${PROJECT_NAME}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || exit 2

ARCHIVE_PATH="/tmp/${ARCHIVE_NAME}"
UPLOADED_ENV_PATH="/tmp/cybershluz-${RELEASE_ID}.env"
REMOTE_SCRIPT_PATH="$(readlink -f -- "${BASH_SOURCE[0]}")"
RELEASES_DIR="${DEPLOY_ROOT}/releases"
SHARED_DIR="${DEPLOY_ROOT}/shared"
RELEASE_DIR="${RELEASES_DIR}/${RELEASE_ID}"
INCOMING_DIR="${RELEASES_DIR}/.${RELEASE_ID}.incoming"
ENV_BACKUP="${SHARED_DIR}/.env.rollback-${RELEASE_ID}"
PREVIOUS_RELEASE=""

cleanup() {
    rm -f -- "${ARCHIVE_PATH}" "${UPLOADED_ENV_PATH}" "${REMOTE_SCRIPT_PATH}" "${ENV_BACKUP}"
    if [[ -d "${INCOMING_DIR}" ]]; then
        rm -rf -- "${INCOMING_DIR}"
    fi
}
trap cleanup EXIT

[[ "${REMOTE_SCRIPT_PATH}" == "/tmp/cybershluz-${RELEASE_ID}.remote-deploy.sh" ]] || {
    echo "Unexpected remote script path" >&2
    exit 2
}

umask 077
cat > "${UPLOADED_ENV_PATH}"

for command_name in docker flock tar; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        echo "Required command is missing on the deployment host: ${command_name}" >&2
        exit 1
    }
done
docker compose version >/dev/null
[[ -s "${ARCHIVE_PATH}" ]] || { echo "Release archive is missing" >&2; exit 1; }
[[ -s "${UPLOADED_ENV_PATH}" ]] || { echo "Environment file is missing" >&2; exit 1; }

mkdir -p -- "${RELEASES_DIR}" "${SHARED_DIR}/ssh_keys"
chmod 700 "${DEPLOY_ROOT}" "${RELEASES_DIR}" "${SHARED_DIR}" "${SHARED_DIR}/ssh_keys"

exec 9>"${DEPLOY_ROOT}/.deploy.lock"
flock --wait 900 9 || {
    echo "Another deployment did not finish within 15 minutes" >&2
    exit 1
}

if [[ -e "${RELEASE_DIR}" ]]; then
    echo "Release ${RELEASE_ID} already exists" >&2
    exit 1
fi
mkdir -- "${INCOMING_DIR}"
tar -xzf "${ARCHIVE_PATH}" -C "${INCOMING_DIR}" --no-same-owner --no-same-permissions
mv -- "${INCOMING_DIR}" "${RELEASE_DIR}"
rm -rf -- "${RELEASE_DIR}/ssh_keys"
ln -s -- "${SHARED_DIR}/ssh_keys" "${RELEASE_DIR}/ssh_keys"

if [[ -f "${SHARED_DIR}/.env" ]]; then
    cp -p -- "${SHARED_DIR}/.env" "${ENV_BACKUP}"
fi
install -m 600 -- "${UPLOADED_ENV_PATH}" "${SHARED_DIR}/.env.next-${RELEASE_ID}"
mv -f -- "${SHARED_DIR}/.env.next-${RELEASE_ID}" "${SHARED_DIR}/.env"

if [[ -L "${DEPLOY_ROOT}/current" ]]; then
    PREVIOUS_RELEASE="$(readlink -f -- "${DEPLOY_ROOT}/current")"
fi

echo "Deploying CyberShluz release ${RELEASE_ID}..."
if ! bash "${RELEASE_DIR}/scripts/deploy.sh" \
    --env-file "${SHARED_DIR}/.env" \
    --project-name "${PROJECT_NAME}" \
    --pull; then
    echo "Deployment failed; restoring the previous release..." >&2
    if [[ -f "${ENV_BACKUP}" ]]; then
        mv -f -- "${ENV_BACKUP}" "${SHARED_DIR}/.env"
    else
        rm -f -- "${SHARED_DIR}/.env"
    fi
    if [[ -n "${PREVIOUS_RELEASE}" && -x "${PREVIOUS_RELEASE}/scripts/deploy.sh" ]]; then
        bash "${PREVIOUS_RELEASE}/scripts/deploy.sh" \
            --env-file "${SHARED_DIR}/.env" \
            --project-name "${PROJECT_NAME}" \
            --pull || echo "Automatic rollback also failed" >&2
    fi
    exit 1
fi

next_link="${DEPLOY_ROOT}/.current-${RELEASE_ID}"
ln -s -- "${RELEASE_DIR}" "${next_link}"
mv -Tf -- "${next_link}" "${DEPLOY_ROOT}/current"
rm -f -- "${ENV_BACKUP}"
echo "Release ${RELEASE_ID} is active at ${DEPLOY_ROOT}/current"
