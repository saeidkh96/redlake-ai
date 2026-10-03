# ADR-001: Adopt Apache Iceberg as the planned table format

- **Status:** Accepted for the roadmap; not implemented in v0.1.0.
- **Date:** 2026-10-03

## Context

RedLake AI needs an open lakehouse table format that works with object storage and distributed engines while keeping data portable. The project is intended to demonstrate modern data-platform engineering relevant to organizations that use open data ecosystems and cloud warehouses.

## Decision

The lakehouse milestone will use **Apache Iceberg** on S3-compatible storage, with Spark as the first compute engine. Raw input remains format-preserving; Bronze/Silver/Gold table creation begins only after the ingestion/catalog foundation is stable.

## Consequences

- Open table metadata, time-travel-capable design, and engine interoperability are central later features.
- Delta Lake remains a valid comparison point but is not simultaneously implemented to avoid duplicate, unverified complexity.
- A catalog strategy (initially an embedded/local catalog, then a service-backed catalog if justified) must be benchmarked and documented in the Iceberg release.
