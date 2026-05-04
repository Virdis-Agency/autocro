# Adapter: Null Abtest

kind: abtest
id: null

The Phase 1 default. This is the **"plan only"** adapter — it does not push anything anywhere. `push_variant` writes a local `experiment.json` file with `status: plan_only` so the variant is preserved in `variants/<slug>/` without any real A/B test being created.

Use this when you want the inner loop to run fully (generating hypotheses, producing patches, scoring composites) but you don't yet have an abtest tool integrated, or you want to review variants manually before pushing any of them.

## requires

```yaml
env: []
command: []
```

## health

1. Always passes.

## capabilities

- push_variant: implemented (plan-only — no remote call)
- get_experiment: implemented (returns a plan-only stub)
- list_experiments: implemented (returns an empty list)
- promote: not_implemented (plan-only cannot ramp traffic)
- archive: not_implemented

## read

### get_experiment(experiment_id)

Return:
```json
{"experiment_id": "<id>",
 "status": "plan_only",
 "visitors": 0, "lift": null,
 "ci_low": null, "ci_high": null, "p": null,
 "started_at": null, "ended_at": null}
```

### list_experiments()

Return: `[]`

## write

### push_variant(slug, patch_path, description, allocation_pct)

Accept the `allocation_pct` argument for contract compatibility (validate it is an integer in `[0, 100]`) but ignore it — the null adapter never reaches a real tool, so any requested allocation is stored for audit and then forgotten. Do not make any network calls. Write a local file to record the plan-only "push":

```
assert isinstance(allocation_pct, int) and 0 <= allocation_pct <= 100
write_json("autocro/variants/<slug>/experiment.json", {
    "experiment_id": "plan_only:<slug>",
    "adapter": "null",
    "allocation": allocation_pct / 100.0,
    "allocation_pct": allocation_pct,
    "started_at": "<now ISO-8601>",
    "status": "plan_only",
    "description": description
})

return {"experiment_id": "plan_only:<slug>",
        "adapter": "null",
        "allocation": allocation_pct / 100.0,
        "allocation_pct": allocation_pct,
        "started_at": "<now ISO-8601>"}
```

Note: `review_mode: "auto"` with the null adapter is rejected by setup-check (auto mode requires a real abtest adapter). So `allocation_pct` will always be `0` in practice when the null adapter is in use, but the argument is required per the contract.

The inner loop will still record `status=pushed` in `results.tsv` and the slug is plan-ready — the human can apply the patch manually or switch `config.adapters.abtest.id` to a real adapter later and re-push.

## idioms

- `plan_only` experiments never reach `winner` or `loser` status automatically. The outer loop skips them.
- `hypothesis_source` should tag these as normal; the `adapter: null` in `experiment.json` is enough to identify them.

## fallbacks

- N/A.
- `mode: fixture`: same as `live` — writes the same plan-only experiment.json.
