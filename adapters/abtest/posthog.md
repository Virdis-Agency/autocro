# Adapter: PostHog Experiments

kind: abtest
id: posthog

Reference adapter for [PostHog Experiments](https://posthog.com/docs/experiments) — PostHog's first-class A/B testing product built on top of feature flags. Uses the same credentials and host as `adapters/analytics/posthog.md` and `adapters/heatmap/posthog.md`, so one PostHog project can cover all three adapter kinds.

## requires

```yaml
env:
  - POSTHOG_API_KEY              # same key as analytics/posthog.md, with "Experiment" write scope
  - POSTHOG_PROJECT_ID           # same project id
  - POSTHOG_HOST                 # OPTIONAL: same default
command: [curl, jq]
```

## health

1. `curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $POSTHOG_API_KEY" "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/experiments/?limit=1"` → expect HTTP 200.
2. Parse: `jq '.results'` → expect an array.
3. Verify the API key has experiment write scope by attempting a dry-run create with an obviously invalid body and checking the error is 400 (validation) not 403 (forbidden). Skip this step if you don't want to touch the write path; accept the risk that push_variant will fail later.
4. If HTTP 401 / 403: stop with `credentials invalid for POSTHOG_API_KEY — give it Experiment:write scope at $POSTHOG_HOST/settings/user-api-keys`.

## capabilities

- push_variant: implemented
- get_experiment: implemented
- list_experiments: implemented
- promote: implemented
- archive: implemented

## read

### get_experiment(experiment_id)

Call:
```bash
curl -sS -H "Authorization: Bearer $POSTHOG_API_KEY" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/experiments/$experiment_id/"
```

Plus a second call to `results/` for statistical data:
```bash
curl -sS -H "Authorization: Bearer $POSTHOG_API_KEY" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/experiments/$experiment_id/results/"
```

Transform:
```
status: PostHog experiments have states {"draft", "running", "complete"}.
  - "draft"    -> "running"   (draft == 0% allocation, not yet launched, which still maps to "running" for the contract)
  - "running"  -> "running"
  - "complete" -> "completed"
  If end_date is set AND status is "running", still map to "completed" (PostHog sometimes lags on state transitions).

visitors:   results.insight[0].count for the variation total
lift:       results.probability[1] - results.probability[0]   (PostHog returns Bayesian probabilities per variant;
                                                                lift is the delta between treatment and control)
ci_low:     results.credible_intervals[1][0]
ci_high:    results.credible_intervals[1][1]
p:          1 - results.probability[1]                         (chanceToWin -> p, same approximation as GrowthBook)
started_at: created_at
ended_at:   end_date (null while running)
```

Return:
```jsonc
{"experiment_id": "42", "status": "running", "visitors": 4200,
 "lift": 0.037, "ci_low": 0.012, "ci_high": 0.061, "p": 0.032,
 "started_at": "2026-03-25T00:00:00Z", "ended_at": null}
```

### list_experiments()

Call:
```bash
curl -sS -H "Authorization: Bearer $POSTHOG_API_KEY" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/experiments/?limit=100"
```

Transform: `.results[]` → each item: `experiment_id = .id` (as string), `status = (same mapping as get_experiment)`, `lift = 0` (lazy; full lift requires a per-experiment results call).

Return:
```jsonc
[{"experiment_id": "42", "status": "running", "lift": 0.0},
 {"experiment_id": "43", "status": "completed", "lift": 0.037}, ...]
```

## write

### push_variant(slug, patch_path, description, allocation_pct)

PostHog Experiments are built on feature flags. Creating an experiment:

1. Validate `allocation_pct` is an integer in `[0, 100]`. Reject otherwise.
2. Create a feature flag with multivariate payload (control + treatment, 50/50 within coverage).
3. Create the experiment attached to the flag, with rollout set to `allocation_pct`.

Combined call:
```bash
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ROLLOUT=${allocation_pct}   # integer 0-100

# Step 1: feature flag
FLAG_KEY="autocro-${slug}"
FLAG=$(curl -sS -X POST \
  -H "Authorization: Bearer $POSTHOG_API_KEY" \
  -H "Content-Type: application/json" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/feature_flags/" \
  -d @- <<EOF
{
  "name": "${slug}",
  "key": "${FLAG_KEY}",
  "filters": {
    "multivariate": {
      "variants": [
        {"key": "control",   "rollout_percentage": 50},
        {"key": "treatment", "rollout_percentage": 50}
      ]
    },
    "groups": [{"rollout_percentage": ${ROLLOUT}, "properties": []}]
  },
  "active": true
}
EOF
)
FLAG_ID=$(echo "$FLAG" | jq -r '.id')

# Step 2: experiment
EXP=$(curl -sS -X POST \
  -H "Authorization: Bearer $POSTHOG_API_KEY" \
  -H "Content-Type: application/json" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/experiments/" \
  -d @- <<EOF
{
  "name": "${slug}",
  "description": "${description} (patch: ${patch_path})",
  "feature_flag_key": "${FLAG_KEY}",
  "parameters": {
    "feature_flag_variants": [
      {"key": "control",   "rollout_percentage": 50},
      {"key": "treatment", "rollout_percentage": 50}
    ]
  },
  "start_date": "${NOW}"
}
EOF
)
EXP_ID=$(echo "$EXP" | jq -r '.id')
```

Transform:
```
experiment_id  = EXP_ID   (cast to string)
adapter        = "posthog"
allocation     = allocation_pct / 100.0
allocation_pct = allocation_pct
started_at     = NOW
```

Return:
```jsonc
{"experiment_id": "42", "adapter": "posthog",
 "allocation": 0.5, "allocation_pct": 50,
 "started_at": "2026-04-10T12:34:56Z"}
```

### promote(experiment_id, allocation)

Update the underlying feature flag's `groups.rollout_percentage`. Only called manually by the human.

```bash
# fetch the flag key from the experiment
FLAG_KEY=$(curl -sS -H "Authorization: Bearer $POSTHOG_API_KEY" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/experiments/$experiment_id/" \
  | jq -r '.feature_flag_key')

# look up the flag id
FLAG_ID=$(curl -sS -H "Authorization: Bearer $POSTHOG_API_KEY" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/feature_flags/?search=$FLAG_KEY" \
  | jq -r '.results[0].id')

# patch rollout
PCT=$(python3 -c "print(int(${allocation} * 100))")
curl -sS -X PATCH \
  -H "Authorization: Bearer $POSTHOG_API_KEY" \
  -H "Content-Type: application/json" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/feature_flags/$FLAG_ID/" \
  -d "{\"filters\": {\"groups\": [{\"rollout_percentage\": ${PCT}, \"properties\": []}]}}"
```

Return:
```jsonc
{"experiment_id": "42", "allocation": 0.5}
```

### archive(experiment_id)

Stop the experiment by setting `end_date` and deactivating the feature flag.

```bash
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
curl -sS -X PATCH \
  -H "Authorization: Bearer $POSTHOG_API_KEY" \
  -H "Content-Type: application/json" \
  "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/experiments/$experiment_id/" \
  -d "{\"end_date\": \"${NOW}\", \"archived\": true}"
```

Return:
```jsonc
{"experiment_id": "42", "status": "stopped"}
```

## idioms

- **PostHog Experiments are built on feature flags.** `push_variant` creates both a flag and an experiment; promote updates the flag. Understanding this matters because if a user manually deletes the flag from the PostHog UI, the experiment becomes orphaned and `get_experiment` may return stale `status: running` indefinitely. Always archive via this adapter, not via the UI.
- **`experiment_id` is numeric.** The adapter stores it as a string (per the schema) but you may need to cast it back to int when calling the PostHog API. The curl calls above use `$experiment_id` directly, which works because bash doesn't type-check.
- **`rollout_percentage` is 0-100, not 0-1.** The adapter divides by 100 on the way in (`get_experiment`) and multiplies by 100 on the way out (`promote`).
- **Bayesian probability vs frequentist p.** Same caveat as `adapters/abtest/growthbook.md`: PostHog reports `probability` (Bayesian chance the variant is better). The adapter approximates `p = 1 - probability`, which is not quite right at the extremes. Flag this in hypothesis.md.
- **Promotion is manual only.** The agent never calls `promote` from the inner loop. Humans ramp.
- **Rate limit**: same ~240 req/min as the other PostHog adapters. Create and archive calls are cheap.
- **Last verified: 2026-04**

## fallbacks

- **HTTP 5xx**: retry once, return empty on failure.
- **HTTP 401 / 403**: stop with credentials invalid.
- **HTTP 404 on get_experiment**: the experiment was deleted upstream. Return a "stopped" stub and log a warning.
- **HTTP 429**: back off 30s, retry once, return empty.
- **Flag creation succeeded but experiment creation failed**: best-effort cleanup — `DELETE /api/projects/:id/feature_flags/:flag_id`. If the cleanup also fails, log both errors to `run.log` and stop the run so the human can clean up manually.
- **`mode: fixture`**: bypass every live call and delegate to `adapters/abtest/fixture.md` behavior: `get_experiment` reads from `fixtures/experiment-sample.json`, `list_experiments` returns the same array, `push_variant` / `promote` / `archive` return deterministic stub responses matching the schema. This is MANDATORY so `skills/validate-adapter.md` can verify the adapter without touching PostHog.
