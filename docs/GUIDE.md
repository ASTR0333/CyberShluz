# Полное руководство по развёртыванию CyberShluz и Moodle в Кибер Инфраструктуре

Это единая инструкция для лабораторного стенда №3 «Подключение хранилища». Она описывает подготовку сети Кибер Инфраструктуры (КИ), создание двух постоянных Ubuntu-ВМ, установку Moodle и CyberShluz, заполнение конфигурации OpenStack/LTI, безопасный SSH-доступ, CI/CD и проверку лабораторной работы.

## 1. Что получится в итоге

- постоянная ВМ `moodle` с Ubuntu Server 24.04, Moodle 5.2, PostgreSQL и Apache;
- постоянная ВМ `cybershluz` с Ubuntu Server 24.04, Docker Compose и этим проектом;
- обе служебные ВМ находятся в сети `local` и доступны администраторам только по SSH-ключу;
- Moodle запускает CyberShluz через LTI 1.3 и получает итоговую оценку;
- CyberShluz через OpenStack API создаёт отдельную сеть и пять лабораторных ВМ для каждого стенда;
- студент работает от пользователя `student` без `sudo`, а проверка и преподаватель — от `labadmin` с отдельным ключом;
- вход `root`, SSH-пароли и keyboard-interactive аутентификация отключены.

Рекомендуемые постоянные DNS-имена:

```text
moodle.example.ru   -> floating IP ВМ moodle
gateway.example.ru  -> floating IP ВМ cybershluz
```

Замените `example.ru` на свой домен. Для LTI нужны стабильные адреса и HTTPS: после регистрации инструмента менять домены нежелательно.

## 2. Что необходимо до начала

- проект и учётная запись в КИ с правами создавать сети, подсети, маршрутизаторы, security groups, floating IP, keypair и ВМ;
- внешняя сеть КИ `Public`;
- свободные квоты для двух постоянных ВМ и одновременно работающих лабораторных стендов;
- два DNS-имени и возможность создать для них A-записи;
- административный компьютер с `ssh-keygen`;
- Git-репозиторий CyberShluz, доступный с ВМ `cybershluz`;
- исходящий доступ из сети `local` к Интернету и OpenStack API.

Для каждой постоянной ВМ разумный минимум: 4 vCPU, 8 ГБ RAM и 30 ГБ диска. Для Moodle при большом количестве студентов увеличьте RAM и диск.

## 3. Подготовка сети в КИ

### 3.1. Создание сети и подсети

В панели КИ откройте раздел вычислительных сетей и создайте сеть `local`. В ней создайте IPv4-подсеть, например:

| Поле | Рекомендуемое значение |
|---|---|
| CIDR | `192.168.50.0/24` |
| Шлюз | `192.168.50.1` |
| DHCP | включён |
| DHCP pool | `192.168.50.100-192.168.50.200` |
| DNS | внутренний DNS организации либо `8.8.8.8`, `1.1.1.1` |

Если публичные DNS-серверы запрещены политикой организации, укажите DNS КИ или корпоративный DNS. Не оставляйте поле DNS пустым.

### 3.2. Создание маршрутизатора

Создайте виртуальный маршрутизатор и настройте:

1. внешний шлюз — сеть `Public`;
2. SNAT — включён;
3. внутренний интерфейс — подсеть сети `local`.

Floating IP не нужен для исходящего трафика через SNAT, но понадобится для входа на постоянные ВМ и для публичного HTTPS.

### 3.3. Security groups постоянных ВМ

Создайте группу `service-vm-sg`:

- входящий TCP/22 — только с административного IP или VPN-подсети;
- входящий TCP/80 и TCP/443 — с требуемых пользовательских сетей;
- входящий ICMP — только если он нужен для диагностики;
- исходящий IPv4 — разрешён.

Не публикуйте наружу PostgreSQL, Redis, Docker API или порт Docker-сокета.

### 3.4. Проверка сети

После создания тестовой Ubuntu-ВМ выполните:

```bash
ip -br addr
ip route
ping -c 3 1.1.1.1
resolvectl query archive.ubuntu.com
```

Ожидается default route через шлюз `local`, успешный ping IP и разрешение имени. Если IP пингуется, а имя нет, исправьте DNS в параметрах подсети и перезапустите сеть или ВМ:

```bash
sudo systemctl restart systemd-networkd systemd-resolved
sudo netplan apply
```

Временная DNS-проверка для интерфейса `ens3`:

```bash
sudo resolvectl dns ens3 8.8.8.8 1.1.1.1
sudo resolvectl domain ens3 '~.'
```

Имя интерфейса уточняется через `ip -br addr`.

## 4. Административный SSH-ключ и две постоянные ВМ

### 4.1. Создание ключа

На доверенном компьютере администратора:

```bash
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/cybershluz-admin -C "cybershluz-admin"
cat ~/.ssh/cybershluz-admin.pub
```

В КИ откройте `Вычисления -> Виртуальные машины -> SSH-ключи`, добавьте содержимое файла `.pub` и назовите ключ `cybershluz-admin`. Закрытый файл `~/.ssh/cybershluz-admin` в КИ не загружайте.

### 4.2. Создание ВМ `moodle`

Создайте ВМ со следующими параметрами:

- имя: `moodle`;
- ОС: Ubuntu Server 24.04 cloud image;
- сеть: `local`;
- security group: `service-vm-sg`;
- SSH key: `cybershluz-admin`;
- floating IP: отдельный адрес из `Public`;
- пользовательские данные: содержимое `infra/cloud-init/service-vm-hardening.yaml`.

### 4.3. Создание ВМ `cybershluz`

Создайте вторую ВМ с такими же параметрами, но именем `cybershluz` и отдельным floating IP. Проект приложения устанавливается только сюда; Moodle устанавливается на предыдущую ВМ.

### 4.4. Проверка защищённого SSH

Для Ubuntu cloud image стандартный пользователь обычно называется `ubuntu`:

```bash
ssh -i ~/.ssh/cybershluz-admin ubuntu@FLOATING_IP
sudo -n true
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|pubkeyauthentication'
```

Ожидаемые значения:

```text
permitrootlogin no
passwordauthentication no
pubkeyauthentication yes
```

Не закрывайте текущую SSH-сессию, пока вход по ключу не проверен во второй сессии.

## 5. Установка CyberShluz

### 5.1. Получение проекта

Подключитесь к ВМ `cybershluz` и выполните:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone <URL_РЕПОЗИТОРИЯ> CyberShluz
cd CyberShluz
chmod +x scripts/configure.sh scripts/deploy.sh
```

### 5.2. Автоматическая установка Docker

На Ubuntu Server 24.04 скрипт `deploy.sh` сам:

1. установит `docker.io` и `docker-compose-v2`, если Docker отсутствует;
2. включит и запустит `docker.service`;
3. добавит текущего пользователя в группу `docker`, если нет доступа к сокету;
4. на первом запуске продолжит работу через `sudo docker`;
5. при следующих входах позволит использовать Docker без `sudo`.

Группа `docker` фактически даёт административный доступ к серверу. Добавляйте в неё только доверенного администратора, не студентов.

Запуск конфигурации и деплоя одной командой:

```bash
./scripts/deploy.sh --configure --pull
```

Для установки пакетов и изменения групп скрипт запросит пароль `sudo`. После первого деплоя переподключитесь по SSH и проверьте:

```bash
groups
docker info
docker compose version
```

### 5.3. Где взять параметры OpenStack

Используйте параметры OpenRC вашего проекта КИ или получите их у администратора проекта. Нужны следующие строки:

```bash
export OS_AUTH_URL=https://<адрес-КИ>:5000/v3
export OS_PROJECT_NAME=<проект>
export OS_USERNAME=<пользователь>
export OS_PASSWORD=<пароль>
export OS_USER_DOMAIN_NAME=<домен>
export OS_PROJECT_DOMAIN_NAME=<домен>
export OS_REGION_NAME=RegionOne
```

В конфигуратор вводятся значения после знака `=`, без `export` и кавычек. Если доступен отдельный сервисный пользователь проекта, используйте его вместо личной учётной записи преподавателя. Пользователю нужны права Nova, Neutron и Glance внутри проекта.

### 5.4. Что вводить в интерактивный конфигуратор

| Запрос | Что вводить | Где найти |
|---|---|---|
| Application environment | `production` | постоянное значение для сервера |
| Public HTTP port | `80` для теста или `8080` при reverse proxy | выбранная схема публикации |
| Docker Compose project name | `cybershluz` | постоянное локальное имя |
| OpenStack Keystone URL | значение `OS_AUTH_URL` | OpenRC, обычно `https://...:5000/v3` |
| OpenStack project name | значение `OS_PROJECT_NAME` | OpenRC/текущий проект КИ |
| OpenStack username | значение `OS_USERNAME` | OpenRC/учётная запись КИ |
| OpenStack password | значение `OS_PASSWORD` | пароль OpenStack API, не пароль Ubuntu |
| OpenStack user domain | значение `OS_USER_DOMAIN_NAME` | OpenRC, в текущем стенде обычно `Hackhaton` |
| OpenStack project domain | значение `OS_PROJECT_DOMAIN_NAME` | OpenRC, в текущем стенде обычно `Hackhaton` |
| OpenStack region | значение `OS_REGION_NAME`, обычно `RegionOne` | OpenRC |
| Default external network | `Public` | имя внешней сети КИ; не `local` |
| Administrative VM user | `labadmin` | создаётся cloud-init лабораторных ВМ |
| Unprivileged VM user | `student` | создаётся cloud-init лабораторных ВМ |
| Legacy image initial SSH user | заводской пользователь Linux-образов либо пусто | нужен только образам без cloud-init; все legacy-образы должны иметь одинаковые bootstrap credentials |
| Legacy image initial SSH password | заводской пароль Linux-образов либо пусто | хранится только в `.env`, после bootstrap вход по паролю отключается |
| Legacy image root password | пароль root для `su` либо пусто | нужен, если заводской SSH-пользователь без sudo; пусто означает тот же пароль |
| SSH bootstrap timeout | `240` | максимальное ожидание доступности legacy Linux-ВМ |
| Stand TTL in hours | `2` | срок обычного стенда |
| Freeze duration in hours | `24` | срок заморозки стенда |
| Maximum projected utilization | `0.9` | предел 90% квоты |

`OS_NETWORK_NAME=Public` означает внешнюю сеть для маршрутизаторов и floating IP. Сеть `local` используется постоянными ВМ и не должна указываться в этом поле.

Скрипт автоматически генерирует `DB_PASSWORD`, `JWT_SECRET_KEY` и `MOODLE_SHARED_SECRET`, сохраняет `.env` с правами `600`. Не коммитьте `.env` в Git.

### 5.5. Проверка деплоя

```bash
docker compose --project-name cybershluz ps
curl -f http://127.0.0.1:80/health
docker compose --project-name cybershluz logs --tail=100 backend celery_worker
```

Если выбран `HOST_PORT=8080`, замените `80` на `8080`. API-документация доступна по `/docs`.
Скрипт развёртывания завершится успешно только после проверки backend и frontend через
`nginx-proxy`; при пересоздании контейнеров proxy автоматически обновляет их Docker DNS-адреса.

## 6. Публикация CyberShluz по HTTPS

Для production рекомендуется оставить контейнеры на `HOST_PORT=8080`, а HTTPS завершать в системном Nginx.

1. Установите пакеты:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

2. Создайте `/etc/nginx/sites-available/cybershluz`:

```nginx
server {
    listen 80;
    server_name gateway.example.ru;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

3. Активируйте конфигурацию и сертификат:

```bash
sudo ln -s /etc/nginx/sites-available/cybershluz /etc/nginx/sites-enabled/cybershluz
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d gateway.example.ru
```

До запуска Certbot A-запись `gateway.example.ru` должна указывать на floating IP этой ВМ, а TCP/80 и TCP/443 должны быть разрешены security group.

## 7. Установка Moodle на второй Ubuntu-сервер

### 7.1. Копирование установщика

С административного компьютера:

```bash
scp -i ~/.ssh/cybershluz-admin \
  infra/moodle/install-moodle-5.2.sh \
  ubuntu@MOODLE_FLOATING_IP:/tmp/
```

Если репозиторий находится только на ВМ `cybershluz`, скопируйте файл оттуда через `scp`, используя разрешённый административный маршрут.

### 7.2. Запуск установки

Подключитесь к ВМ `moodle` и выполните:

```bash
chmod +x /tmp/install-moodle-5.2.sh
export MOODLE_URL='https://moodle.example.ru'
export MOODLE_ADMIN_PASSWORD='ДЛИННЫЙ-УНИКАЛЬНЫЙ-ПАРОЛЬ-НЕ-МЕНЕЕ-14-СИМВОЛОВ'
export MOODLE_ADMIN_EMAIL='admin@example.ru'
export MOODLE_SITE_NAME='CyberShluz Moodle'
export MOODLE_SHORT_NAME='CyberShluz'
sudo -E /tmp/install-moodle-5.2.sh
```

Скрипт устанавливает Moodle 5.2 (`MOODLE_502_STABLE`), PHP 8.3, PostgreSQL 16, Apache и cron. `moodledata` размещается вне web root, код после установки становится read-only для веб-сервера. Пароль БД сохраняется только в `/root/moodle-install-credentials` с правами `600`.

### 7.3. HTTPS Moodle

До выдачи сертификата A-запись `moodle.example.ru` должна указывать на floating IP Moodle:

```bash
sudo apt-get install -y certbot python3-certbot-apache
sudo certbot --apache -d moodle.example.ru
sudo certbot renew --dry-run
```

Откройте `https://moodle.example.ru`, войдите пользователем `moodleadmin` и паролем из `MOODLE_ADMIN_PASSWORD`.

## 8. Связь Moodle с CyberShluz через LTI 1.3

### 8.1. Регистрация инструмента в Moodle

Откройте:

`Администрирование сайта -> Плагины -> Модули деятельности -> Внешний инструмент -> Управление инструментами -> Настроить инструмент вручную`.

Укажите:

| Поле Moodle | Значение |
|---|---|
| Tool name | `CyberShluz` |
| Tool/Launch URL | `https://gateway.example.ru/api/v1/lti/launch` |
| LTI version | `LTI 1.3` |
| Public key type | `Keyset URL` |
| Public keyset/JWKS URL | `https://gateway.example.ru/api/v1/lti/jwks` |
| Initiate login URL | `https://gateway.example.ru/api/v1/lti/login` |
| Redirection URI | `https://gateway.example.ru/api/v1/lti/launch` |
| Assignment and Grade Services | включить использование сервиса оценок |

Сохраните инструмент. Moodle покажет `Client ID` и `Deployment ID`; скопируйте их без пробелов.

### 8.2. Заполнение LTI в `.env`

На ВМ `cybershluz` откройте `.env` и добавьте или измените:

```dotenv
LTI_ISSUER=https://moodle.example.ru
LTI_CLIENT_ID=<CLIENT_ID_ИЗ_MOODLE>
LTI_DEPLOYMENT_ID=<DEPLOYMENT_ID_ИЗ_MOODLE>
LTI_AUTH_LOGIN_URL=https://moodle.example.ru/mod/lti/auth.php
LTI_AUTH_TOKEN_URL=https://moodle.example.ru/mod/lti/token.php
LTI_KEYSET_URL=https://moodle.example.ru/mod/lti/certs.php
LTI_FRONTEND_BASE_URL=https://gateway.example.ru
LTI_PRIVATE_KEY_PATH=/app/ssh_keys/lti/tool_private.pem
LTI_KEY_ID=kibershluz-tool-key-1
LTI_GRADE_LAB_ID=3
```

Если Moodle установлен в подпути `/moodle`, этот подпуть должен присутствовать в `LTI_ISSUER` и во всех Moodle endpoints. Не добавляйте завершающий `/` к базовым URL.

Примените изменения:

```bash
./scripts/deploy.sh
```

CyberShluz генерирует свой LTI RSA-ключ при первом обращении и публикует открытую часть через `/api/v1/lti/jwks`. Закрытый ключ остаётся в каталоге `ssh_keys/lti` на сервере.

### 8.3. Добавление активности в курс

В нужном курсе Moodle:

1. включите режим редактирования;
2. добавьте деятельность `Внешний инструмент`;
3. выберите предварительно настроенный `CyberShluz`;
4. включите передачу имени, email и оценки, если это допускает политика организации;
5. сохраните и откройте активность от тестового студента.

После LTI launch студент попадает в форму параметров стенда. Оценка отправляется в Moodle только после полного результата `PASSED`.

## 9. Лабораторные образы и интерактивное развёртывание

Текущие значения для лабораторной №3:

| Роль | Образ в КИ | UUID | Flavor | IP по умолчанию |
|---|---|---|---|---|
| L-MS | `2_TMP_L-MS_Debian11.11_09.2025.qcow2` | `521b868a-ac28-4eb9-9f77-562df86f18db` | `small` | `10.10.0.10` |
| L-NFS | `2_TMP_L-NFS_CentOS7_08.2025.qcow2` | `3ae20dd5-ae96-4c0b-b8bd-7e3cb225191b` | `tiny` | `10.10.0.70` |
| L-PGSQL | `2_TMP_L-PGSQL_CentOS7_08.2025.qcow2` | `dd37703a-8af3-4619-bbd3-c6b69d5e7e8d` | `tiny` | `10.10.0.55` |
| W-DC | `2_TMP_W-DC_WinSrvStd19_10.2025.qcow2` | `6ac5ebae-979e-48f2-bc4f-5d0a9a701650` | `medium` | `10.10.0.5` |
| V-HYPERV | `2_TMP_V-HYPERV_WinSrvStd19_10.2025.qcow2` | `c3947f72-fe13-489a-8073-676ffdf9f859` | `large` | `10.10.0.65` |

Перед боевым запуском проверьте:

- Linux-образы содержат cloud-init и OpenSSH;
- Windows-образы содержат Cloudbase-Init и OpenSSH Server;
- имена flavor существуют именно в выбранном проекте;
- квоты проекта позволяют создать выбранные ресурсы;
- внешняя сеть называется `Public` либо пользователь выбрал правильное имя в форме.

CyberShluz передаёт cloud-init/Cloudbase-Init через Nova `user_data`
в Base64 и включает config drive. Так один административный keypair
стенда попадает на все ВМ даже при недоступном metadata proxy. ВМ,
созданные старой версией без маркера SSH-политики, при повторном
развёртывании создаются заново: изменить `user_data` уже запущенной ВМ нельзя.

В форме можно изменить CIDR, gateway, DHCP pool, DNS, external network, образы, выбрать flavor из списка OpenStack и задать статические IP. DHCP pool не должен пересекаться со статическими IP. L-MS обязательна как компонент лабораторной топологии. Floating IP получает только L-MS.

## 10. Модель SSH-доступа лабораторного стенда

Для каждого стенда CyberShluz автоматически создаёт две OpenStack keypair:

- `key-stand<ID>-admin` — пользователь `labadmin`, `sudo` без пароля, доступ только преподавателю и автоматической проверке;
- `key-stand<ID>-student` — пользователь `student`, без `sudo` и групп `sudo`/`wheel`, используется для key-only SSH на Linux-ВМ стенда.

Дополнительно:

- root заблокирован;
- парольная и keyboard-interactive SSH-аутентификация отключена;
- студент может одним действием добавить личный публичный ключ на L-MS; приватная часть системе не передаётся;
- security group разрешает key-only SSH к Floating IP L-MS;
- PostgreSQL, NFS и RDP не публикуются напрямую в Интернет;
- RDP на W-DC и V-HYPERV доступен только во внутренней сети. Для работы с W-DC
  студент поднимает туннель через L-MS:

```bash
ssh -L 13389:<внутренний-IP-W-DC>:3389 student@<Floating-IP-L-MS>
```

После этого RDP-клиент подключается к `localhost:13389`.

Обычный сценарий для студента не требует локального RDP-клиента и ручного
туннеля: в карточке каждой роли с префиксом `W` доступна кнопка «Веб-консоль»,
которая открывает штатную консоль виртуальной машины в панели КИ. Backend
проверяет владельца стенда, допустимый префикс роли и формирует ссылку по
сохранённому UUID выбранного инстанса. Адрес панели задаётся в `.env`:

```dotenv
OS_DASHBOARD_URL=https://edu.cyber-infrastructure.ru:8800
```

Для просмотра консоли браузер может запросить вход в панель КИ. Ручная команда
выше остаётся резервным способом диагностики.

Для legacy-образа L-MS без cloud-init задайте `VM_BOOTSTRAP_USER` и
`VM_BOOTSTRAP_PASSWORD` в серверном `.env`. CyberShluz сначала пытается войти под
заводским пользователем с Nova-ключом администратора, а заводской пароль использует как
резервный способ. Если этот пользователь отсутствует в sudoers, bootstrap использует
`su`; отличный от пользовательского пароль root задаётся через
`VM_BOOTSTRAP_ROOT_PASSWORD`. Затем он создаёт `labadmin` и `student`, устанавливает разные
ключи, удаляет административные права у студента и отключает парольный SSH.
Пароль не сохраняется в БД стенда и не возвращается через API.

Перед статусом `READY` шлюз обязательно подключается к L-MS по её
Floating IP обоими ключами, проверяет
`sudo` у администратора и отсутствие `sudo` у студента. Если ни cloud-init, ни
одноразовый bootstrap не обеспечили эту политику, развёртывание завершается
ошибкой. Сохранённые ключи повторно используются при Celery retry и не меняются
у уже созданных ВМ.

## 11. Проверка лабораторной №3

### 11.1. Автоматические проверки

- L-MS доступна по SSH через собственный Floating IP;
- hostname L-MS точно соответствует роли и домену `.cyberprotect.test`;
- на L-MS слушает порт веб-консоли `9877`;
- на W-DC через SSH/PowerShell запущены Storage Node Service, Catalog Browser Service и Elasticsearch;
- на W-DC существует `C:\Backups`.

После результата `PASSED` стенд и отчёт сохраняются, пока пользователь явно не нажмёт «Завершить работу»; это не позволяет фоновой очистке стереть итог раньше, чем студент его увидит.

### 11.2. Исправления команд методички

- вместо типографского `su –` используйте `su -`;
- вместо `firewall-cmd –-reload` используйте `firewall-cmd --reload`;
- после `hostnamectl set-hostname ...` команда `newgrp` не нужна; при необходимости новой login shell используйте `exec "$SHELL" -l`;
- для L-MS используется точное имя `l-ms.cyberprotect.test`;
- формулировка «регистрация с маркетом» является опечаткой: имеется в виду регистрация с маркером.

## 12. Эксплуатация, резервное копирование и откат

Обновление:

```bash
git pull --ff-only
./scripts/deploy.sh --pull
```

Просмотр состояния:

```bash
docker compose --project-name cybershluz ps
docker compose --project-name cybershluz logs --tail=200 backend celery_worker nginx-proxy
```

Остановка без удаления данных:

```bash
./scripts/deploy.sh --down
```

Резервная копия PostgreSQL:

```bash
docker compose --project-name cybershluz exec -T db \
  pg_dump -U lab_admin lab_orchestrator > lab_orchestrator.sql
```

Для отката переключитесь на проверенный tag/commit и снова запустите `./scripts/deploy.sh`. Не используйте `docker compose down -v`, если вы намеренно не хотите удалить БД, Redis и другие именованные volumes.

Несколько окружений на одном сервере:

```bash
./scripts/deploy.sh --env-file .env.staging --project-name cybershluz-staging
./scripts/deploy.sh --env-file .env.production --project-name cybershluz-production
```

Для каждого окружения нужны отдельные `HOST_PORT`, env-файл, Compose project name, домен и LTI-регистрация.

## 13. CI/CD GitHub Actions

Workflow выполняет backend lint/tests, frontend lint/build, secret scan, Compose build и затем по SSH выкладывает проверенный commit на `mvp_admin@10.46.128.246`. Каждая выкладка хранится как отдельный release в `/home/mvp_admin/cybershluz-deploy`; текущая версия доступна через ссылку `current`. Одновременные деплои блокируются, а при неудаче скрипт пытается вернуть предыдущий release.

`10.46.128.246` входит в частный диапазон `10.0.0.0/8`. Поэтому job деплоя запускается на self-hosted runner с labels `self-hosted`, `linux`, `cybershluz`, который видит этот адрес. CI-проверки выполняются на GitHub-hosted runner. Если labels отличаются, задайте variable `DEPLOY_RUNNER` как JSON-массив, например `["self-hosted","linux","production"]`.

Один раз подготовьте сервер:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker mvp_admin
```

После добавления в группу нужно заново войти по SSH. Проверьте под пользователем `mvp_admin`, что `docker info` и `docker compose version` работают без `sudo`. Добавьте отдельный public SSH-ключ CI в `/home/mvp_admin/.ssh/authorized_keys`.

В GitHub Environment `production` задайте:

- secret `ENV_FILE` — полное содержимое `.env` соответствующего окружения;
- secret `DEPLOY_SSH_PRIVATE_KEY` — приватный SSH-ключ CI без passphrase;
- secret `DEPLOY_KNOWN_HOSTS` — заранее проверенная строка host key для `10.46.128.246`;
- variable `COMPOSE_PROJECT_NAME` — например `cybershluz`;
- optional variable `DEPLOY_RUNNER` — JSON-массив labels runner;
- optional variable `DEPLOY_HEALTHCHECK_URL` — URL проверки, если сервис опубликован не на порту 80.

Host key получите и сверьте его fingerprint через консоль сервера, после чего сохраните строку в `DEPLOY_KNOWN_HOSTS`:

```bash
ssh-keyscan -H 10.46.128.246 > known_hosts
ssh-keygen -lf known_hosts
```

Пуш в `main` автоматически деплоит `production`. Для ручного запуска используйте **Actions → CI/CD → Run workflow**. В GitHub Environment `production` рекомендуется включить required reviewers.

## 14. Частые ошибки

### `Temporary failure resolving archive.ubuntu.com`

Это ошибка DNS. Сравните:

```bash
ping -c 3 1.1.1.1
resolvectl status
resolvectl query archive.ubuntu.com
```

Если IP доступен, исправьте DNS подсети `local`. Если IP недоступен, проверьте default route, интерфейс маршрутизатора, внешний gateway `Public`, SNAT и исходящие правила security group.

### `Docker daemon is unavailable`

```bash
systemctl status docker --no-pager
docker info
sudo docker info
ls -l /var/run/docker.sock
groups
```

Новый `deploy.sh` автоматически запускает службу, добавляет пользователя в группу `docker` и продолжает первый запуск через `sudo docker`. Для постоянного применения группы переподключитесь по SSH.

### `401`, `unknown issuer` или LTI launch возвращает ошибку

Сверьте без приблизительных значений:

- `LTI_ISSUER` с URL Moodle (`$CFG->wwwroot`);
- `LTI_CLIENT_ID` и `LTI_DEPLOYMENT_ID` с карточкой инструмента Moodle;
- Moodle endpoints и HTTPS-сертификаты;
- доступность `/api/v1/lti/login`, `/api/v1/lti/launch` и `/api/v1/lti/jwks` с браузера пользователя Moodle.

### Образ или flavor не найден

Проверьте имя в интерфейсе КИ или выберите ресурс в интерактивной форме. UUID образов приведены в разделе 9, но проект должен иметь к ним доступ.

## 15. Финальный чек-лист

- [ ] `local` подключена к маршрутизатору, внешний gateway — `Public`, SNAT включён.
- [ ] На обеих Ubuntu-ВМ работают маршрут и DNS.
- [ ] SSH по паролю и root отключены, вход по ключу проверен.
- [ ] У Moodle и CyberShluz есть разные floating IP и DNS A-записи.
- [ ] HTTPS-сертификаты обоих доменов действительны.
- [ ] `docker compose ps` показывает healthy/running сервисы.
- [ ] `/health` CyberShluz возвращает успешный ответ.
- [ ] OpenStack credentials соответствуют нужному проекту и домену.
- [ ] В `.env` внешняя сеть указана как `Public`.
- [ ] LTI Client ID, Deployment ID, issuer и endpoints перенесены из Moodle без ошибок.
- [ ] Тестовый студент может открыть внешнюю активность и создать стенд.
- [ ] Студент не имеет `sudo`, root/password SSH не работают.
- [ ] После `PASSED` тестовая оценка появляется в журнале Moodle.

Официальные материалы: [Кибер Инфраструктура — создание ВМ](https://docs.cyberprotect.ru/ru-RU/CyberInfrastructure/latest/admin/creating-virtual-machines.html), [добавление SSH-ключей](https://docs.cyberprotect.ru/ru-RU/CyberInfrastructure/latest/admin/adding-ssh-keys.html), [виртуальные маршрутизаторы](https://docs.cyberprotect.ru/ru-RU/CyberInfrastructure/latest/admin/creating-virtual-routers.html), [Docker Engine для Ubuntu](https://docs.docker.com/engine/install/ubuntu/), [Moodle 5.2](https://moodledev.io/general/releases/5.2).
