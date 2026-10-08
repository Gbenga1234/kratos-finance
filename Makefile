.PHONY: up down logs test shell container-shell

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api worker

test:
	pytest

shell:
	docker compose exec api python -m app.shell

container-shell:
	docker compose exec api /bin/sh
