.PHONY: up down logs test migrate shell container-shell

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api worker scheduler

migrate:
	docker compose run --rm migrate

test:
	pytest

shell:
	docker compose exec api python -m app.shell

container-shell:
	docker compose exec api /bin/sh
