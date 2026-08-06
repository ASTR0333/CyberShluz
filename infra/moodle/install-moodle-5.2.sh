#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run as root: sudo -E bash $0" >&2
    exit 1
fi

: "${MOODLE_URL:?Set MOODLE_URL, for example https://moodle.example.edu}"
: "${MOODLE_ADMIN_PASSWORD:?Set a strong MOODLE_ADMIN_PASSWORD}"

MOODLE_ADMIN_EMAIL="${MOODLE_ADMIN_EMAIL:-admin@example.invalid}"
MOODLE_SITE_NAME="${MOODLE_SITE_NAME:-CyberShluz Moodle}"
MOODLE_SHORT_NAME="${MOODLE_SHORT_NAME:-CyberShluz}"
MOODLE_BRANCH="${MOODLE_BRANCH:-MOODLE_502_STABLE}"
MOODLE_DIR="/opt/moodle"
MOODLE_DATA="/var/lib/moodledata"
DB_NAME="moodle"
DB_USER="moodle"
DB_PASSWORD="$(openssl rand -hex 32)"

if [[ "${#MOODLE_ADMIN_PASSWORD}" -lt 14 ]]; then
    echo "MOODLE_ADMIN_PASSWORD must contain at least 14 characters" >&2
    exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    apache2 git openssl postgresql postgresql-client cron \
    php8.3 php8.3-cli libapache2-mod-php8.3 php8.3-pgsql php8.3-curl \
    php8.3-zip php8.3-gd php8.3-xml php8.3-intl php8.3-mbstring \
    php8.3-soap php8.3-bcmath php8.3-ldap php8.3-opcache \
    graphviz aspell ghostscript

runuser -u postgres -- psql --set=ON_ERROR_STOP=1 --set=db_password="${DB_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE moodle LOGIN PASSWORD %L', :'db_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'moodle') \gexec
ALTER ROLE moodle WITH LOGIN PASSWORD :'db_password';
SELECT 'CREATE DATABASE moodle OWNER moodle ENCODING ''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'moodle') \gexec
SQL

if [[ ! -d "${MOODLE_DIR}/.git" ]]; then
    git clone --depth 1 --branch "${MOODLE_BRANCH}" \
        https://github.com/moodle/moodle.git "${MOODLE_DIR}"
fi

install -d -m 0770 -o www-data -g www-data "${MOODLE_DATA}"
chown -R www-data:www-data "${MOODLE_DIR}"

cat >/etc/php/8.3/apache2/conf.d/99-moodle.ini <<'EOF'
max_input_vars = 5000
memory_limit = 512M
upload_max_filesize = 256M
post_max_size = 256M
max_execution_time = 300
EOF

cat >/etc/apache2/sites-available/moodle.conf <<EOF
<VirtualHost *:80>
    ServerName $(printf '%s' "${MOODLE_URL}" | sed -E 's#^https?://##; s#/.*$##')
    DocumentRoot ${MOODLE_DIR}/public

    <Directory ${MOODLE_DIR}/public>
        Options FollowSymLinks
        AllowOverride All
        Require all granted
        DirectoryIndex index.php
    </Directory>

    <FilesMatch \.php$>
        SetHandler application/x-httpd-php
    </FilesMatch>

    ErrorLog \${APACHE_LOG_DIR}/moodle-error.log
    CustomLog \${APACHE_LOG_DIR}/moodle-access.log combined
</VirtualHost>
EOF

a2dissite 000-default
a2ensite moodle
a2enmod rewrite headers ssl
systemctl restart apache2

if [[ ! -f "${MOODLE_DIR}/config.php" ]]; then
    runuser -u www-data -- php "${MOODLE_DIR}/admin/cli/install.php" \
        --non-interactive \
        --lang=ru \
        --wwwroot="${MOODLE_URL}" \
        --dataroot="${MOODLE_DATA}" \
        --dbtype=pgsql \
        --dbhost=127.0.0.1 \
        --dbname="${DB_NAME}" \
        --dbuser="${DB_USER}" \
        --dbpass="${DB_PASSWORD}" \
        --fullname="${MOODLE_SITE_NAME}" \
        --shortname="${MOODLE_SHORT_NAME}" \
        --adminuser=moodleadmin \
        --adminpass="${MOODLE_ADMIN_PASSWORD}" \
        --adminemail="${MOODLE_ADMIN_EMAIL}" \
        --agree-license
fi

chown -R root:root "${MOODLE_DIR}"
chown root:www-data "${MOODLE_DIR}/config.php"
chmod 0640 "${MOODLE_DIR}/config.php"
find "${MOODLE_DIR}" -type d -exec chmod 0755 {} +
find "${MOODLE_DIR}" -type f -exec chmod 0644 {} +
chmod 0640 "${MOODLE_DIR}/config.php"

cat >/etc/cron.d/moodle <<EOF
* * * * * www-data /usr/bin/php ${MOODLE_DIR}/admin/cli/cron.php >/dev/null 2>&1
EOF
chmod 0644 /etc/cron.d/moodle

install -m 0600 /dev/null /root/moodle-install-credentials
printf 'database=%s\nuser=%s\npassword=%s\n' \
    "${DB_NAME}" "${DB_USER}" "${DB_PASSWORD}" \
    >/root/moodle-install-credentials

echo "Moodle ${MOODLE_BRANCH} installed for ${MOODLE_URL}."
echo "Database credentials: /root/moodle-install-credentials (mode 600)."
echo "If MOODLE_URL uses HTTPS, configure a trusted TLS certificate before exposing the site."
