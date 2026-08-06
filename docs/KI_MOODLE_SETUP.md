# Кибер Инфраструктура: Moodle, CyberShluz и безопасный SSH

## Итоговая схема

- Постоянная ВМ `moodle`: Ubuntu 24.04, Moodle 5.2, PostgreSQL 16, публичный DNS/HTTPS.
- Постоянная ВМ `cybershluz`: Ubuntu 24.04, Docker Compose и этот репозиторий.
- Обе постоянные ВМ подключены к сети `local`; маршрутизатор связывает `local` с физической внешней сетью.
- Лабораторные ВМ создаются CyberShluz через стандартные Keystone/Nova/Neutron/Glance API OpenStack.
- Для каждого студенческого стенда создаётся отдельная сеть, подсеть, маршрутизатор и floating IP только для `L-MS`.

Студент не должен получать SSH-доступ к ВМ Moodle или CyberShluz. Он работает с ними только через HTTPS.

## Образы лабораторной №3

| Роль | Имя образа в КИ | UUID со скриншота |
|---|---|---|
| L-MS | `2_TMP_L-MS_Debian11.11_09.2025.qcow2` | `521b868a-ac28-4eb9-9f77-562df86f18db` |
| L-NFS | `2_TMP_L-NFS_CentOS7_08.2025.qcow2` | `3ae20dd5-ae96-4c0b-b8bd-7e3cb225191b` |
| L-PGSQL | `2_TMP_L-PGSQL_CentOS7_08.2025.qcow2` | `dd37703a-8af3-4619-bbd3-c6b69d5e7e8d` |
| W-DC | `2_TMP_W-DC_WinSrvStd19_10.2025.qcow2` | `6ac5ebae-979e-48f2-bc4f-5d0a9a701650` |
| V-HYPERV | `2_TMP_V-HYPERV_WinSrvStd19_10.2025.qcow2` | `c3947f72-fe13-489a-8073-676ffdf9f859` |

Перед первым запуском убедитесь, что Linux-образы содержат `cloud-init` и OpenSSH, а Windows-образы — Cloudbase-Init и OpenSSH Server. Без этого КИ не сможет внедрить ключи. CyberShluz теперь останавливает небезопасный деплой, если проверка ключевого входа на L-MS не прошла.

## Ключ администратора для постоянных ВМ

На доверенном компьютере администратора:

```bash
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/cybershluz-admin -C "cybershluz-admin"
cat ~/.ssh/cybershluz-admin.pub
```

В панели КИ откройте «Вычисления → Виртуальные машины → SSH-ключи», добавьте публичную часть и назовите её `cybershluz-admin`. Закрытый ключ в КИ не загружайте.

При создании обеих Ubuntu-ВМ:

1. Выберите сеть `local` и административный SSH-ключ `cybershluz-admin`.
2. В поле пользовательских данных вставьте содержимое `infra/cloud-init/service-vm-hardening.yaml`.
3. Назначьте каждой ВМ floating IP или проброс через внешний reverse proxy. Для LTI обе системы должны обращаться друг к другу по стабильным DNS-именам.
4. Разрешите SSH/22 только с административной сети или конкретного IP. Для пользователей публикуйте только HTTPS/443.

После запуска проверьте:

```bash
ssh -i ~/.ssh/cybershluz-admin ubuntu@MOODLE_FLOATING_IP
sudo -n true
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|pubkeyauthentication'
```

Ожидается `permitrootlogin no`, `passwordauthentication no`, `pubkeyauthentication yes`.

## Установка Moodle на второй Ubuntu-сервер

Скопируйте только установочный скрипт на Moodle-ВМ или возьмите его из репозитория на ВМ CyberShluz:

```bash
scp -i ~/.ssh/cybershluz-admin \
  infra/moodle/install-moodle-5.2.sh \
  ubuntu@MOODLE_FLOATING_IP:/tmp/
```

На Moodle-ВМ:

```bash
chmod +x /tmp/install-moodle-5.2.sh
export MOODLE_URL='https://moodle.example.edu'
export MOODLE_ADMIN_PASSWORD='ЗАМЕНИТЬ-НА-ДЛИННЫЙ-СЕКРЕТ'
export MOODLE_ADMIN_EMAIL='admin@example.edu'
sudo -E /tmp/install-moodle-5.2.sh
```

Скрипт устанавливает Moodle 5.2 из ветки `MOODLE_502_STABLE`, PHP 8.3, PostgreSQL 16 и Apache; web root направляется на `/opt/moodle/public`, `moodledata` находится вне web root, а cron запускается каждую минуту. Код Moodle после установки недоступен для записи пользователю веб-сервера.

Для production настройте DNS и доверенный TLS-сертификат. Не регистрируйте LTI по временным IP и HTTP: смена URL нарушит issuer/redirect URI, а токены и оценки должны передаваться по HTTPS.

## Регистрация CyberShluz в Moodle

В Moodle добавьте LTI 1.3 External Tool со значениями:

- Tool/Launch URL: `https://gateway.example.edu/api/v1/lti/launch`
- Initiate login URL: `https://gateway.example.edu/api/v1/lti/login`
- Redirection URI: `https://gateway.example.edu/api/v1/lti/launch`
- Public keyset/JWKS URL: `https://gateway.example.edu/api/v1/lti/jwks`
- LTI version: `LTI 1.3`
- Services: Assignment and Grade Services, отправка score.

Полученные в Moodle `Client ID` и `Deployment ID`, а также Moodle issuer/endpoints перенесите в `.env` CyberShluz. После этого перезапустите стек командой `./scripts/deploy.sh`.

## SSH-модель лабораторных стендов

- `labadmin`: отдельный ключ на стенд, `sudo` без пароля; приватный ключ доступен только преподавателю/администратору.
- `student`: отдельный ключ на стенд, без групп `sudo`/`wheel` и без записей sudoers; этот ключ использует web-terminal и автоматическая пользовательская сессия.
- Личный публичный ключ студента можно добавить из интерфейса. Он дописывается в `student/.ssh/authorized_keys` через административный ключ, приватная часть остаётся у студента.
- `root` заблокирован, SSH по паролю и keyboard-interactive отключены.
- Автопроверка использует `labadmin`, поскольку ей нужны привилегированные read-only проверки сервисов; студент этот ключ не получает.

На Windows Cloudbase-Init создаёт `labadmin` в группе Administrators и обычного `student`, устанавливает их разные ключи и отключает парольную SSH-аутентификацию. Если в конкретном шаблоне Cloudbase-Init отключён или не выполняет PowerShell user-data, образ необходимо исправить до использования.

После обновления CyberShluz старые уже созданные стенды не имеют отдельного студенческого ключа. Их следует штатно удалить через интерфейс и создать заново; постоянные Moodle/CyberShluz ВМ это не затрагивает.
