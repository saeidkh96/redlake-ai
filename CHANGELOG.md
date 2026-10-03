# Changelog

All notable, implemented changes to RedLake AI are documented here. Planned work belongs in [docs/ROADMAP.md](docs/ROADMAP.md), not in release claims.

## [0.1.0] - 2026-10-03

### Added

- Dataset catalog and versioned data contracts.
- CSV/JSON batch ingestion with schema profiling and quality evidence.
- Raw/quarantine object-store semantics with local filesystem and S3-compatible adapters.
- SHA-256 checksums and idempotency-key replay protection.
- FastAPI/OpenAPI API; JSON logs, request IDs, Prometheus metrics, health/readiness probes.
- PostgreSQL-oriented Alembic catalog migration and local MinIO/PostgreSQL/Prometheus Compose definition.
- Automated API/domain tests, Ruff linting, GitHub Actions CI, source-package script, architecture and roadmap documentation.

### Known boundaries

- v0.1.0 contains no API connector, Kafka, Spark, Iceberg, dbt, Airflow, SQL serving, MLflow, LangGraph agent, Kubernetes deployment, RBAC, or multi-tenancy.
- Compose runtime validation is pending a Docker-capable host; the Compose YAML is validated and the database migration is exercised against a fresh SQLite database.

