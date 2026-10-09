FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --chown=app:app pyproject.toml alembic.ini ./
COPY --chown=app:app app ./app
COPY --chown=app:app migrations ./migrations
RUN pip install --no-cache-dir '.[api]'

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"]

CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn_worker.UvicornWorker", "--workers", "2", "--bind", "0.0.0.0:8000", "--timeout", "30", "--graceful-timeout", "30", "--keep-alive", "5", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-", "--error-logfile", "-"]
