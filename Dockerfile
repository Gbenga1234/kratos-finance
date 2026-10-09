FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --chown=app:app pyproject.toml ./
COPY --chown=app:app app ./app
RUN pip install --no-cache-dir '.[api]'

USER app

EXPOSE 8000

CMD ["gunicorn", "app.main:app", "--worker-class", "uvicorn_worker.UvicornWorker", "--workers", "2", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-"]
