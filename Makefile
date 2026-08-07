.PHONY: install run lint fmt test build deploy

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

build:
	@echo "Phase 2: docker build comes here"

deploy:
	@echo "Phase 3: terraform + kubectl come here"
