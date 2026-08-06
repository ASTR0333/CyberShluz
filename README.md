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

Шаги по настройке репозитория:

    Обновите список пакетов:
    Убедитесь, что у вас есть актуальная информация о доступных пакетах.

    sudo apt-get update

    Установите необходимые утилиты для добавления репозиториев:

    sudo apt-get install ca-certificates curl

    Создайте каталог для ключей шифрования APT:

    sudo install -m 0755 -d /etc/apt/keyrings

    Скачайте официальный GPG-ключ Docker:

    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc

    Установите разрешение на ключ:

    sudo chmod a+r /etc/apt/keyrings/docker.asc

    Добавьте репозиторий Docker:

    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
    sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    Снова обновите список пакетов:

    sudo apt-get update

    И теперь поставьте нужные пакеты для Docker:

    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    В конце проверьте, что всё работает, запустив тестовый контейнер. У нас это будет “hello-word”,  где в консоль выведется информация и контейнер завершит свою работу:

    sudo docker run hello-world
