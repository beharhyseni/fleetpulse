.PHONY: install run lint fmt test build deploy db-up db-down migrate revision

install:
	pip install -r requirements.txt -r requirements-dev.txt

run:
	uvicorn app.main:app --reload --no-access-log

lint:
	ruff check .
	ruff format --check .
	mypy app

fmt:
	ruff format .
	ruff check . --fix

test:
	pytest

db-up:
	docker compose up -d db

db-down:
	docker compose down

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

seed:
	python -m app.seed --devices 25 --hours 72 --reset

build:
	docker build -t fleetpulse:dev .

deploy:
	@echo "deploys ship via git push -- see .github/workflows/ci.yml"
