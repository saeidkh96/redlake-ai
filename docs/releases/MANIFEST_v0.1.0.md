# Release Manifest — v0.1.0

## Artifact

- Product: RedLake AI
- Version: `0.1.0`
- Release name: **Catalog & Batch Ingestion Foundation**
- Archive command: `python scripts/package_release.py`
- Archive outputs: `dist/redlake-ai-v0.1.0.zip` and `dist/redlake-ai-v0.1.0.zip.sha256`

## Scope evidence

| Requirement | Evidence |
| --- | --- |
| Catalog and data contracts | FastAPI endpoints + Alembic `20261003_0001` migration |
| CSV / JSON ingestion | Domain parser and API integration tests |
| Quality and schema validation | Stored profile/quality report; rejection/quarantine test |
| Immutable raw persistence | Filesystem object-store atomic write path + API test |
| Idempotency | SHA-256 + repeated-key and changed-content test cases |
| Observability | JSON logging, `X-Request-ID`, Prometheus `/metrics`, health endpoints |
| CI | `.github/workflows/ci.yml` runs lint, test/coverage, and Docker build |

## Validation record

| Check | Result |
| --- | --- |
| `python -m ruff check .` | Passed |
| `python -m pytest --cov=app --cov-report=term-missing` | Passed: 10 tests, 85% total coverage |
| `alembic upgrade head` on a fresh SQLite database | Passed |
| Docker Compose YAML parse | Passed |
| Docker Compose runtime / image build | Not run: Docker is unavailable in this build environment |
| Archive hygiene | Verified: no `.env`, data, coverage cache, or package metadata included |

## Release limitations

Refer to [v0.1.0 release notes](v0.1.0.md) and the [architecture limitations](../ARCHITECTURE.md#known-v010-limitations). The next implementation milestone is v0.2.0: reusable REST API connector framework.

