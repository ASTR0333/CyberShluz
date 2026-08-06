# Развёртывание CyberShluz на сервере

## Требования

- Ubuntu 22.04/24.04 или другой Linux с Docker Engine 24+ и Docker Compose v2.
- 4 CPU, 8 ГБ RAM и не менее 30 ГБ свободного диска для самого оркестратора.
- Доступ сервера к Keystone/Nova/Neutron/Glance OpenStack и к виртуальным машинам стенда.
- Открытый входящий TCP-порт, указанный в `HOST_PORT` (по умолчанию `80`). PostgreSQL и Redis наружу не публикуются.

## Первый запуск

```bash
git clone <URL_РЕПОЗИТОРИЯ> CyberShluz
cd CyberShluz
chmod +x scripts/configure.sh scripts/deploy.sh
./scripts/configure.sh
./scripts/deploy.sh --pull
```

Конфигуратор интерактивно запрашивает OpenStack-проект, учётные данные, домены, region, внешнюю сеть и TTL. Пароли лабораторных образов не используются: доступ к ВМ создаётся только через две пары SSH-ключей OpenStack. Секреты приложения генерируются автоматически, файл `.env` создаётся с правами `600`.

После запуска проверьте:

```bash
docker compose --project-name cybershluz ps
curl -f http://127.0.0.1/health
docker compose --project-name cybershluz logs --tail=100 backend celery_worker
```

Интерфейс будет доступен по `http://SERVER_IP:HOST_PORT/`, OpenAPI — по `/docs`.

## Обновление и откат

```bash
git pull --ff-only
./scripts/deploy.sh
```

Данные PostgreSQL и расписание Celery находятся в именованных Docker volumes. Команда `./scripts/deploy.sh --down` останавливает контейнеры, но не удаляет volumes. Перед обновлением схемы рекомендуется сделать резервную копию:

```bash
docker compose --project-name cybershluz exec -T db \
  pg_dump -U lab_admin lab_orchestrator > lab_orchestrator.sql
```

Для отката переключите Git на предыдущий проверенный tag/commit и снова выполните `./scripts/deploy.sh`. Не используйте `docker compose down -v`, если резервная копия не создана.

## Несколько окружений на одном сервере

Используйте отдельные env-файлы, порты и Compose project names:

```bash
./scripts/deploy.sh --env-file .env.staging --project-name cybershluz-staging
./scripts/deploy.sh --env-file .env.production --project-name cybershluz-production
```

Это изолирует имена контейнеров, сети и volumes. Фиксированные `container_name` в Compose не используются.

## GitHub Actions

Единый workflow запускает lint, тесты и сборку обоих приложений, после чего выполняет один согласованный деплой всего Compose-стека. Для GitHub Environment (`production` или `staging`) задайте:

- secret `ENV_FILE` — полное содержимое соответствующего `.env`;
- variable `COMPOSE_PROJECT_NAME` — например `cybershluz-production`;
- variable `DEPLOY_RUNNER` — JSON-массив labels self-hosted runner, например `["self-hosted","linux","production"]`.

Self-hosted runner должен иметь Docker Compose v2 и право запускать Docker. Ручной запуск `workflow_dispatch` позволяет выбрать окружение и отключить фактический деплой, оставив только CI.

## Проверка лабораторной №3

Автопроверка подключается к L-MS по Floating IP, а к L-NFS и L-PGSQL — через L-MS как bastion. Она проверяет точные hostname, порт 9877, четыре firewall-порта, `snapapi`, службы Acronis/Cyber Protect и каталог `/BackupL`.

Три пункта из методички нельзя достоверно проверить текущим SSH-доступом: Windows-службы W-DC, регистрацию W-DC и наличие RepoW/RepoL в веб-консоли. Они вынесены в явный ручной чек-лист. Пока он не подтверждён, результат — `REVIEW_REQUIRED`; оценка в Moodle не отправляется и стенд не очищается.
