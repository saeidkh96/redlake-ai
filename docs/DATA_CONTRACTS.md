# Data Contracts in v0.1.0

## Contract shape

```json
{
  "version": "v0.1.0",
  "allow_extra_fields": false,
  "fields": [
    {"name": "event_id", "data_type": "integer", "required": true},
    {"name": "event_type", "data_type": "string", "required": true},
    {"name": "metadata", "data_type": "object", "required": false}
  ]
}
```

Supported types are `string`, `integer`, `number`, `boolean`, `object`, and `array`. A `number` accepts observed integers and floating-point values. A new contract version becomes active atomically for its dataset and supersedes the prior active contract.

## Checks

Every parse runs the following error-level checks:

1. Input has at least one nonblank record.
2. Field names are unique.
3. All contract fields exist in the source.
4. No unexpected fields exist when `allow_extra_fields` is `false`.
5. Required fields have no null values.
6. Observed non-null values are compatible with the declared type.

The result is a stored report, not a transient log. Failed checks route the exact original file to `quarantine/` and set the run to `rejected`.

## Contract evolution rules

- Additive fields should be introduced as optional first.
- Do not reuse a version number with different semantics.
- Make a new version before changing data types or making an optional field required.
- Send producers a new idempotency key after source/contract repair.

