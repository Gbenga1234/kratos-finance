from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.tasks import process_transfer


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.main.engine", engine)
    monkeypatch.setattr("app.tasks.SessionLocal", test_session_factory)
    monkeypatch.setattr(
        "app.main.celery_app.send_task",
        lambda *args, **kwargs: None,
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def transfer_payload(**overrides: object) -> dict[str, object]:
    return {
        "source_account_id": "acct-source",
        "destination_account_id": "acct-destination",
        "amount": "12.50",
        "currency": "usd",
        **overrides,
    }


def test_create_and_retrieve_transfer(client: TestClient) -> None:
    response = client.post("/transfers", json=transfer_payload())

    assert response.status_code == 202
    created = response.json()
    assert created["amount"] == "12.50"
    assert created["currency"] == "USD"
    assert created["status"] == "pending"

    retrieved = client.get(f"/transfers/{created['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["id"] == created["id"]


def test_default_worker_completes_simulated_transfer(client: TestClient) -> None:
    from app.celery_app import celery_app

    response = client.post("/transfers", json=transfer_payload())
    transfer_id = response.json()["id"]

    assert celery_app.conf.task_default_queue == "default"
    assert process_transfer.run(transfer_id) == "completed"
    assert client.get(f"/transfers/{transfer_id}").json()["status"] == "completed"


def test_idempotency_key_returns_existing_transfer(client: TestClient) -> None:
    headers = {"Idempotency-Key": "transfer-request-1"}
    first = client.post("/transfers", json=transfer_payload(), headers=headers)
    second = client.post(
        "/transfers",
        json=transfer_payload(amount="99.00"),
        headers=headers,
    )

    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert Decimal(second.json()["amount"]) == Decimal("12.50")


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": "0"},
        {"currency": "US"},
        {"destination_account_id": "acct-source"},
    ],
)
def test_rejects_invalid_transfer(
    client: TestClient,
    overrides: dict[str, str],
) -> None:
    response = client.post("/transfers", json=transfer_payload(**overrides))

    assert response.status_code == 422


def test_unknown_transfer_returns_404(client: TestClient) -> None:
    response = client.get("/transfers/missing")

    assert response.status_code == 404
