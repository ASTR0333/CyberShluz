#!/usr/bin/env bash
















set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"


if [[ -t 1 ]]; then
    C_GREEN=$'\033[0;32m'; C_RED=$'\033[0;31m'; C_YELLOW=$'\033[0;33m'
    C_BLUE=$'\033[0;34m'; C_DIM=$'\033[2m'; C_RESET=$'\033[0m'
else
    C_GREEN=''; C_RED=''; C_YELLOW=''; C_BLUE=''; C_DIM=''; C_RESET=''
fi

info()  { echo "${C_BLUE}[deploy]${C_RESET} $*"; }
ok()    { echo "${C_GREEN}[deploy] ✓${C_RESET} $*"; }
warn()  { echo "${C_YELLOW}[deploy] ⚠${C_RESET} $*"; }
fail()  { echo "${C_RED}[deploy] ✗${C_RESET} $*" >&2; exit 1; }


REBUILD=0
SHOW_LOGS=0
ACTION="up"
for arg in "$@"; do
    case "${arg}" in
        --rebuild) REBUILD=1 ;;
        --logs)    SHOW_LOGS=1 ;;
        --down)    ACTION="down" ;;
        -h|--help)
            sed -n '2,18p' "$0"
            exit 0
            ;;
        *) fail "Неизвестный флаг: ${arg}" ;;
    esac
done


info "Проверка зависимостей…"
command -v docker >/dev/null 2>&1 || fail "docker не найден. Установи: https://docs.docker.com/engine/install/ubuntu/"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 не найден. Установи плагин docker-compose-plugin."

if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon не отвечает. Запусти 'sudo systemctl start docker' или добавь пользователя в группу docker: 'sudo usermod -aG docker \$USER && newgrp docker'"
fi
ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) + Compose $(docker compose version --short)"

if [[ "${ACTION}" == "down" ]]; then
    info "Останавливаю стек…"
    docker compose down
    ok "Стек остановлен."
    exit 0
fi


if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        cp .env.example .env
        warn ".env не было — создан из .env.example. ОТРЕДАКТИРУЙ OS_PASSWORD, JWT_SECRET_KEY, MOODLE_SHARED_SECRET и запусти скрипт снова."
        exit 1
    else
        fail "Нет ни .env, ни .env.example. Восстанови репозиторий."
    fi
fi


if grep -q $'\r' .env 2>/dev/null; then
    warn ".env содержит CRLF — конвертирую в LF."
    sed -i 's/\r$//' .env
fi
ok ".env найден"


mkdir -p ssh_keys



if [[ "$(stat -c '%u' ssh_keys 2>/dev/null || echo 0)" != "1000" ]]; then
    if [[ "${EUID}" -eq 0 ]]; then
        chown -R 1000:1000 ssh_keys
        chmod 700 ssh_keys
        ok "ssh_keys/ — владелец 1000:1000, mode 700"
    else
        warn "ssh_keys/ не принадлежит UID 1000. Попробую sudo chown — потребуется пароль."
        sudo chown -R 1000:1000 ssh_keys && sudo chmod 700 ssh_keys \
            && ok "ssh_keys/ — владелец 1000:1000, mode 700" \
            || warn "chown не удался — backend может не суметь писать ключи. Запусти вручную: sudo chown -R 1000:1000 ssh_keys && sudo chmod 700 ssh_keys"
    fi
else
    ok "ssh_keys/ — владелец уже 1000"
fi


HOST_PORT="$(grep -E '^HOST_PORT=' .env | head -1 | cut -d= -f2 | tr -d ' "'\''')"
HOST_PORT="${HOST_PORT:-80}"
if command -v ss >/dev/null 2>&1; then
    if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${HOST_PORT}$"; then
        warn "Порт ${HOST_PORT}/tcp на хосте уже занят. Либо останови занимающий процесс, либо смени HOST_PORT в .env."
        warn "Кто слушает: $(ss -ltnp 2>/dev/null | awk -v p=":${HOST_PORT}$" '$4 ~ p {print $NF; exit}')"
    fi
fi


if [[ ${REBUILD} -eq 1 ]]; then
    info "Форсированный rebuild (--no-cache)…"
    docker compose build --no-cache
fi

info "Сборка и запуск стека…"
docker compose up -d --build


info "Ожидаю готовности backend (до 60 с)…"
for i in {1..30}; do
    if docker compose exec -T backend curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        ok "backend здоров"
        break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
        warn "backend не ответил на healthcheck за 60 с. Логи:"
        docker compose logs --tail=50 backend
    fi
done


PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "${PUBLIC_IP}" ]] && PUBLIC_IP="localhost"

echo
ok "Готово."
echo "   UI:    ${C_BLUE}http://${PUBLIC_IP}:${HOST_PORT}/${C_RESET}"
echo "   Docs:  ${C_BLUE}http://${PUBLIC_IP}:${HOST_PORT}/docs${C_RESET}"
echo "   Logs:  ${C_DIM}docker compose logs -f${C_RESET}"
echo

if [[ ${SHOW_LOGS} -eq 1 ]]; then
    docker compose logs --tail=200
fi
