
FROM python:3.12-slim


LABEL maintainer="P2 Team"
LABEL description="Lab Orchestrator Backend - FastAPI + Celery + Async Deploy"


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"


WORKDIR /app


RUN sed -i 's/deb.debian.org/mirror.yandex.ru/g' /etc/apt/sources.list.d/debian.sources || true && \
    echo 'Acquire::Retries "10";' > /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::http::Timeout "20";' >> /etc/apt/apt.conf.d/80-retries && \
    echo 'Acquire::ftp::Timeout "20";' >> /etc/apt/apt.conf.d/80-retries


RUN apt-get -o Acquire::ForceIPv4=true update && \
    apt-get -o Acquire::ForceIPv4=true install -y --no-install-recommends \
    gcc \
    libc6-dev \
    python3-dev \
    postgresql-client \
    curl \
    ansible \
    openssh-client \
    sshpass \
    && rm -rf /var/lib/apt/lists/*


RUN python -m venv /opt/venv


COPY requirements.txt .
RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


COPY . .


RUN groupadd -r appuser || true && \
    useradd -r -g appuser -u 1000 -m appuser && \
    mkdir -p /var/lib/celery /app/ssh_keys && \
    chown -R appuser:appuser /app /var/lib/celery /app/ssh_keys && \
    chmod 700 /app/ssh_keys


ENV ANSIBLE_HOST_KEY_CHECKING=False

USER appuser


EXPOSE 8000


HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1


CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
