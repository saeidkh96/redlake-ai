.PHONY: install lint test run up down migrate package

install:
	python -m pip install -e ".[dev]"

lint:
	python -m ruff check .

test:
	python -m pytest --cov=app --cov-report=term-missing

run:
	uvicorn app.main:app --reload

up:
	docker compose up --build

down:
	docker compose down --volumes

migrate:
	alembic upgrade head

package:
	python scripts/package_release.py

