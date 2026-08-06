# CyberShluz

Оркестратор лабораторного стенда №3 «Подключение хранилища»: FastAPI, Celery, React, PostgreSQL, Redis, Ansible и OpenStack.

Система создаёт отдельную Neutron-сеть для каждого стенда и разворачивает пять машин из методической топологии. Перед запуском пользователь может выбрать CIDR, DHCP-пул, внешний network, образы, flavor’ы и статические IP. Backend валидирует адреса и рассчитывает прогноз квоты по фактически выбранным flavor’ам.

## Быстрый запуск на Linux-сервере

```bash
chmod +x scripts/configure.sh scripts/deploy.sh
./scripts/configure.sh
./scripts/deploy.sh --pull
```

Полная инструкция, обновление, откат, несколько окружений и настройка GitHub Actions описаны в [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

Схема двух постоянных ВМ в Кибер Инфраструктуре, установка Moodle 5.2, список новых образов и модель SSH-доступа описаны в [docs/KI_MOODLE_SETUP.md](docs/KI_MOODLE_SETUP.md).

Сверка автоматической проверки с методичкой и найденные опечатки команд собраны в [docs/LAB3_REVIEW.md](docs/LAB3_REVIEW.md).

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
