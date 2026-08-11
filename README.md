# CyberShluz

Оркестратор лабораторного стенда №3 «Подключение хранилища»: FastAPI, Celery, React, PostgreSQL, Redis, Ansible и OpenStack.

Система создаёт отдельную Neutron-сеть для каждого стенда и разворачивает пять машин из методической топологии. Перед запуском пользователь может выбрать CIDR, DHCP-пул, внешний network, образы, конфигурации из списка доступных flavor’ов OpenStack и статические IP. Backend валидирует адреса и рассчитывает прогноз квоты по фактически выбранным flavor’ам.

## Быстрый запуск на Linux-сервере

```bash
chmod +x scripts/configure.sh scripts/deploy.sh
./scripts/deploy.sh --configure --pull
```

На Ubuntu Server 24.04 скрипт сам устанавливает Docker Engine и Compose v2, запускает демон и выдаёт текущему администратору доступ к Docker-сокету.

Подготовка Кибер Инфраструктуры, две постоянные ВМ, Moodle/LTI, точное заполнение конфигурации, SSH-безопасность, лабораторные образы, CI/CD, проверка и эксплуатация собраны в одном [полном руководстве](docs/GUIDE.md).

## Проверки разработки

```bash
cd backend
python -m pip install -r requirements.txt
ruff check app tests
pytest -q

cd ../frontend
npm ci
npm run lint
npm run build
```

Техническое описание прежней версии проекта сохранено в [docs.html](docs.html).

