# Adapter: Fixture Abtest

kind: abtest
id: fixture

Simulates a complete abtest tool lifecycle using `fixtures/experiment-sample.json`. Used by end-to-end smoke tests to exercise both the inner loop's `push_variant` handoff AND the outer loop's `get_experiment` poll without any real A/B testing tool.

On `push_variant`, it records a deterministic experiment ID and writes a local `experiment.json`. On `get_experiment`, it looks up the experiment in `fixtures/experiment-sample.json` and returns a pre-shaped result payload — usually a mix of winners, losers, and still-measuring experiments to exercise the outer loop's promotion logic.

## requires

```yaml
env: []
command: [cat]
```

## health

1. Confirm `autocro/fixtures/experiment-sample.json` exists and parses.
2. Confirm it has at least one `completed` entry and one `running` entry so both outer-loop branches (promote, keep-measuring) are exercised. Statuses must be drawn from the adapter contract: `running | completed | stopped` (see `adapters/README.md:199` / `harness/schemas/abtest.json`).

## capabilities

- push_variant: implemented
- get_experiment: implemented
- list_experiments: implemented
- promote: implemented (no-op; logs only)
- archive: implemented (no-op; logs only)

## read

### get_experiment(experiment_id)

```
data = read_json("autocro/fixtures/experiment-sample.json")
for entry in data["experiments"]:
    if entry["experiment_id"] == experiment_id:
        return entry
# Unknown experiment ID — return a default "still running" stub that
# matches the abtest contract status enum (running | completed | stopped).
return {"experiment_id": experiment_id, "status": "running",
        "visitors": 100, "lift": 0.0,
        "ci_low": -0.05, "ci_high": 0.05, "p": 0.9,
        "started_at": "2026-04-01T00:00:00Z", "ended_at": null}
```

### list_experiments()

```
return read_json("autocro/fixtures/experiment-sample.json")["experiments"]
```

## write

### push_variant(slug, patch_path, description, allocation_pct)

```
assert isinstance(allocation_pct, int) and 0 <= allocation_pct <= 100
exp_id = f"fixture:{slug}"
now_iso = <ISO-8601 current time>
allocation = allocation_pct / 100.0
write_json("autocro/variants/<slug>/experiment.json", {
    "experiment_id": exp_id,
    "adapter": "fixture",
    "allocation": allocation,
    "allocation_pct": allocation_pct,
    "started_at": now_iso,
    "description": description
})
return {"experiment_id": exp_id, "adapter": "fixture",
        "allocation": allocation, "allocation_pct": allocation_pct,
        "started_at": now_iso}
```

The `allocation_pct` field is echoed back in the response so
`skills/validate-adapter.md` and the end-to-end smoke test can assert on
the exact value the caller requested (e.g. 50 in auto mode).

### promote(experiment_id, allocation)

Log only. Return: `{"experiment_id": experiment_id, "allocation": allocation}`.

### archive(experiment_id)

Log only. Return: `{"experiment_id": experiment_id, "status": "archived"}`.

## idioms

- Fixture experiment IDs always start with `fixture:` so the analysis notebook can filter them out of real-data aggregations.
- `fixtures/experiment-sample.json` deliberately contains a mix of statuses so outer-loop polling is exercised in smoke tests.

## fallbacks

- **File missing**: health fails.
- **Malformed JSON**: stop with a clear parse error.
