# Kratos Finance

A Python fintech starter for submitting and tracking simulated account-to-account
transfers. It does not connect to a bank, payment processor, or other payment rail,
and it does not move funds.

## Run with containers

Docker Compose starts the FastAPI API, a Celery worker consuming the `default`
queue, PostgreSQL, and Redis:

```sh
docker compose up --build
```

The API is available at <http://localhost:8000>; interactive OpenAPI docs are at
<http://localhost:8000/docs>.
If port 8000 is already in use, set `API_PORT` to a free host port, for example
`API_PORT=18000 docker compose up --build`.

```sh
curl -X POST http://localhost:8000/transfers \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-transfer-001' \
  -d '{"source_account_id":"acct-a","destination_account_id":"acct-b","amount":"25.00","currency":"USD"}'
```

The response contains a transfer ID and starts with `pending`. The worker records
a simulated `completed` result, which can be read using
`GET /transfers/{transfer_id}`. Reusing an idempotency key returns its original
transfer.

Useful commands:

```sh
make logs             # Follow API and Celery worker logs
make shell            # Open a Python shell with app models and DB session factory
make container-shell  # Open /bin/sh in the running API container
make down
```

## Run locally

Requires Python 3.11 or newer. Start a local PostgreSQL/Redis service or provide
their URLs, then install and run:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
celery -A app.celery_app:celery_app worker --loglevel=INFO --queues=default
```

Without environment overrides, the API uses a local SQLite file and Celery uses
Redis at `localhost:6379`. Configure `DATABASE_URL`, `CELERY_BROKER_URL`,
`CELERY_RESULT_BACKEND`, and `LOG_LEVEL` as needed. Logs are emitted to stdout.

Run tests with `pytest`.

## Scope and production notes

This is a runnable development scaffold, not a production-ready financial
service. Before handling real money or financial data, add identity and access
controls, account ownership and balance/ledger invariants, migrations, secrets
management, reconciliation, audit retention, rate limits, and a compliant,
idempotent payment-rail integration. The Compose credentials are development
defaults and must not be reused in production.
