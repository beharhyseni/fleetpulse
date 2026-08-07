.PHONY: install run lint fmt test build deploy db-up db-down migrate revision

install:
	pip install -r requirements.txt -r requirements-dev.txt

run:
	uvicorn app.main:app --reload

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
	docker compose up -d --wait db

db-down:
	docker compose down

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

build:
	@echo "Phase 2: docker build comes here"

deploy:
	@echo "Phase 3: terraform + kubectl come here"
