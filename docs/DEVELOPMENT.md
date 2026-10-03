# Development and Verification

## Local mode

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
alembic upgrade head
make lint
make test
make run
```

The default local configuration is intentionally self-contained: SQLite stores catalog metadata and the filesystem adapter stores raw/quarantine objects under `data/`. Schema changes are applied through Alembic; `AUTO_CREATE_SCHEMA` is reserved for isolated tests.

## Compose mode

```bash
docker compose up --build
curl http://localhost:8000/api/v1/health/ready
curl http://localhost:8000/metrics
```

Compose runs PostgreSQL, MinIO, the API, and Prometheus. The API executes `alembic upgrade head` before it starts. The MinIO bootstrap container creates the `redlake-raw` bucket once.

## Schema changes

The application models are in `app/db/models.py`; migrations are source-controlled in `alembic/versions/`.

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Review generated migrations manually. Production-style Compose startup does not call `create_all`; that convenience is reserved for local/test mode.

## Test layers

| Layer | Purpose |
| --- | --- |
| Domain tests | Parsing, inferred profiles, data-quality semantics |
| API tests | Catalog, contracts, uploads, idempotency, HTTP outcomes |
| Compose smoke test | Database + S3-compatible object storage + migration integration |
| Future integration/load tests | Kafka, Spark, Airflow, Iceberg, and operational SLOs |

## Release hygiene

Before a release:

1. Run `make lint` and `make test`.
2. Run the documented Compose smoke workflow.
3. Update `README.md`, architecture/roadmap documents, and release note.
4. Create the clean source archive with `python scripts/package_release.py`.
5. Commit the verified milestone, tag the version, and publish a GitHub release when a remote repository exists.
