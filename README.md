# Kratos Finance

Kratos Finance is a Python service for authenticated, simulated account-to-account
transfer requests. It does **not** hold funds, maintain spendable balances, connect
to a payment rail, or move real money. It is not a licensed financial product or
a complete production financial service.

## Local container stack

Copy `.env.example` to `.env`, change the local-only database password in both
PostgreSQL variables and `DATABASE_URL`, then start the stack:

```sh
cp .env.example .env
docker compose up --build
```

Compose builds a Gunicorn/Uvicorn API image and a separate Celery image. It also
runs versioned database migrations, PostgreSQL, Redis, a Celery worker, and the
single Celery Beat scheduler that dispatches the durable outbox. The API listens
on `http://localhost:8000`; interactive API docs are enabled only in development.
Set `API_PORT` if the host port is occupied.

In development, transfer endpoints still require a valid OIDC access token; the
sample environment intentionally does not bypass authentication. Configure a
development identity provider and its exact issuer, API audience, and HTTPS JWKS
URL in `.env`. Tokens must be signed with RS256 or ES256 and include `iss`, `aud`,
`sub`, `iat`, and `exp`. Requests are scoped to the validated token subject.

```sh
curl -X POST http://localhost:8000/transfers \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-transfer-001' \
  -d '{"source_account_id":"acct-a","destination_account_id":"acct-b","amount":"25.00","currency":"USD"}'
```

`GET /transfers/{transfer_id}` returns only transfers belonging to the
authenticated subject. Amounts are decimal values with two decimal places,
currencies are explicitly allowlisted, and the maximum is configured in cents
(`MAX_TRANSFER_AMOUNT`, default `10000000`, or 100,000.00 units). A repeated
idempotency key with the same request returns the original transfer; reusing it
for a different request returns `409`.

The transfer row and its outbox event commit together. The scheduler retries
outbox publication; Celery delivery is at-least-once, and the database transition
is idempotent. The recorded `completed` state means only that the simulation task
ran.

Useful commands:

```sh
make logs             # Follow API, worker, and scheduler logs
make migrate          # Run versioned migrations
make shell            # Open a Python shell with app models and DB session factory
make container-shell  # Open /bin/sh in the running API container
make test             # Run tests
make down             # Stop services; retain the named database volume
```

## Local Python development

Requires Python 3.11 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[api,dev]'
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.celery_app:celery_app worker --loglevel=INFO --queues=default
celery -A app.celery_app:celery_app beat --loglevel=INFO
pytest
```

Set `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, the three
`OIDC_*` values, and `TRUSTED_HOSTS` for the environment. For a local test
provider, use its real JWKS endpoint; do not add an authentication bypass.

## Deployment boundary

The Compose file is a local development topology, **not a production deployment
recipe**. `APP_ENV=production` fails closed unless configured with a remote
PostgreSQL URL using `sslmode=verify-full`, explicit trusted hosts, an HTTPS OIDC
issuer/JWKS endpoint and audience, and remote authenticated TLS Redis URLs. The
development Compose Redis and `.env.example` credentials are not production
secrets.

Before any production use, an accountable team must still:

- Deploy into a managed, supported environment with TLS ingress, network
  segmentation, managed secrets, protected Redis, and a production OIDC tenant.
- Establish tenant/account ownership and authorization against a real account
  registry. Account identifiers in this demo are caller-supplied labels.
- Add external rate limits, abuse controls, operational alerting, trace/metric
  export, incident response, audited access, retention, and tested encrypted
  backups/disaster recovery.
- Pin reviewed base-image digests and dependency lockfiles, scan artifacts,
  attest builds, and promote immutable releases.
- Set organization-specific privacy, security, legal, and regulatory controls.
- Design a separately reviewed double-entry ledger, reconciliation, settlement,
  fraud controls, and licensed payment-provider integration before considering
  any real-money use.

Legacy transfer rows migrated from the pre-migration schema are marked
`legacy-unowned` and are deliberately not visible through the authenticated API.
Review and resolve those records through a controlled administrative process;
the migration does not guess ownership.
