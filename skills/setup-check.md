# Skill: setup-check

The first thing `program.md` runs. Validates `config.yaml`, verifies every referenced adapter file exists, and confirms every `*_env` environment variable is actually set before the inner loop touches anything. On any problem, surface a structured, actionable error to the human and stop. No degraded-mode startup on user errors.

Invoked by `program.md` step 1. Calls `harness/yaml_to_json.py`, `harness/validate.py`, and (for adapter capability validation) `skills/validate-adapter.md`.

## Why this exists

Without this skill, the inner loop would start with a silently-wrong config or a missing env var, producing confusing output hours into a run. The rule is: every failure mode must stop setup with a line-addressed message that tells the human WHAT is wrong, WHERE, and HOW to fix it.

## Steps

### 0. Confirm framework file integrity

Before touching the user's config, confirm the framework's own load-bearing files are present. If any are missing, the run will start cleanly and crash mid-iteration when one of these is invoked. List that must exist:

- `autocro/harness/judge-rubric.md` (used by `skills/pre-validate.md` for every variant)
- `autocro/harness/check_results_row.py` (used by the inner loop before every TSV append)
- `autocro/harness/check_path.py` (used by `skills/generate-variant.md` for deny-glob enforcement)
- `autocro/harness/validate.py` (used by step 2 below)
- `autocro/harness/yaml_to_json.py` (used by step 2 below)
- `autocro/harness/schemas/{analytics,heatmap,abtest,config}.json` (all four schema files)

If `config.mode: fixture` is set (re-checked after step 2), also require:

- `autocro/fixtures/analytics-sample.json`
- `autocro/fixtures/heatmap-sample.json`
- `autocro/fixtures/experiment-sample.json`

Any missing file → stop with:

```
SETUP CHECK FAILED: framework file missing
missing: <path>
fix: this file ships with the autocro framework. Restore it from a fresh
     clone of the repo (git checkout HEAD -- <path>), or re-clone the
     framework if you've made unrelated local changes you want to keep.
setup stopped.
```

### 1. Confirm `config.yaml` exists

```
ls autocro/config.yaml
```

If missing, stop with:

```
SETUP CHECK FAILED: config.yaml not found
expected: autocro/config.yaml
fix: cp autocro/config.example.yaml autocro/config.yaml
     then edit it to set project.root, goal.event, goal.target_paths,
     and the adapter ids you want.
setup stopped.
```

### 2. Convert `config.yaml` to JSON and run schema validation

```bash
python3 autocro/harness/yaml_to_json.py autocro/config.yaml \
  | python3 autocro/harness/validate.py config --stdin
```

This runs two layers of checks:

- `yaml_to_json.py` parses the config with a minimal YAML subset parser (stdlib only). If the config uses unsupported YAML features, it stops with a clear line number.
- `validate.py config` runs the draft-07 schema from `harness/schemas/config.json` plus post-schema rules: weights sum ≈ 1.0, `discard < push`, and a literal-secret heuristic for `config.adapters.*`.

On any failure, exit code is 2 (user error) or 3 (load/parser error). Surface the stderr block verbatim to the human and stop. Exit code 4 (internal helper crash) is NOT the user's fault — log a warning in `run.log` and continue, but mark the config as "unvalidated" so later steps know to be cautious.

### 3. Verify mode / adapter consistency

If `config.mode == "fixture"`, at least one of `config.adapters.{analytics, heatmap, abtest}.id` must be non-null. Every adapter (real or fixture) is contractually required to implement a `## fallbacks > mode: fixture` branch (see `adapters/README.md` and the "MANDATORY for `skills/validate-adapter.md`" line in every reference adapter), so a real adapter id like `"ga4"` is valid in fixture mode — it just routes through the adapter's fixture fallback. With no adapter loaded at all, the inner loop has nothing to call and will produce empty hypotheses silently. If every adapter id is `null`, stop with:

```
SETUP CHECK FAILED: fixture mode requires at least one adapter
config.mode = "fixture"
config.adapters.analytics.id = <value>
config.adapters.heatmap.id   = <value>
config.adapters.abtest.id    = <value>
fix: set at least one of adapters.{analytics,heatmap,abtest}.id to a non-null
     value. The simplest offline smoke test sets all three to "fixture"; a
     real adapter id (e.g. "ga4") also works in fixture mode because every
     adapter implements a mandatory fixture fallback. See README.md.
setup stopped.
```

### 4. Verify adapter files exist for every non-null, non-fixture id

For each `config.adapters.<kind>.id` that is neither `null` nor `"fixture"`:

```
ls autocro/adapters/<kind>/<id>.md
```

Missing file → stop with:

```
SETUP CHECK FAILED: adapter file not found
config.adapters.<kind>.id = "<id>"
expected: autocro/adapters/<kind>/<id>.md
exists: no
fix: either (a) set adapters.<kind>.id: null in config.yaml to run without that data source,
            (b) run skills/author-adapter.md to create it, or
            (c) git pull — the reference adapter may not be checked in yet.
setup stopped.
```

### 5. Parse each loaded adapter's `requires.env` list and verify the vars are set

For each adapter file loaded in step 4, read its `requires` block (the YAML frontmatter inside `## requires`) and for every name in `env`, check `os.environ`:

```bash
python3 -c 'import os, sys; print("SET" if os.environ.get(sys.argv[1]) else "MISSING")' VAR_NAME
```

Or, equivalently, the agent can check its own environment. A missing env var stops setup with:

```
SETUP CHECK FAILED: required env var not set
adapter: autocro/adapters/<kind>/<id>.md
missing: <VAR_NAME>
declared at: adapters/<kind>/<id>.md :: requires.env
fix: export <VAR_NAME>=<value>
     then re-run program.md setup.
setup stopped.
```

If `config.mode: fixture` is set, skip this check — fixture mode is supposed to run without real credentials. Note the skip in `run.log`.

### 6. Run `skills/validate-adapter.md` against each loaded adapter

For each non-null adapter, invoke `skills/validate-adapter.md` with the adapter path and the current `config.mode`. That skill runs each declared capability once (against live APIs or fixture data, per mode) and pipes the response to `harness/validate.py` to confirm the returned shape matches the contract.

Failure → stop setup with the full error block from validate.py's stderr. See `skills/validate-adapter.md` for the exact error format and what it tells the human about fixing the adapter's `## read` section.

### 7. Validate `workflow` config and opt-in pre-validation helpers

Run checks 7a–7f and 7h **only if** `config.workflow` is set. Run check 7g (opt-in helper existence) **whenever** `config.prevalidation.lighthouse.enabled` or `config.prevalidation.persona.enabled` is true — those flags live under `prevalidation`, not `workflow`, so a config that enables them without a `workflow:` block must still hit 7g. The first three workflow checks (a, b, c) and 7g are hard failures; the rest are warnings.

**a) Auto-push threshold floor (hard).** If `workflow.auto_push_threshold < prevalidation.thresholds.push`, stop with:

```
SETUP CHECK FAILED: workflow.auto_push_threshold is below the push gate
config.workflow.auto_push_threshold = <value>
config.prevalidation.thresholds.push = <push>
fix: set auto_push_threshold >= <push>. Auto mode is supposed to be
     MORE selective than the base push gate, not less.
setup stopped.
```

**b) Auto mode requires an abtest adapter (hard).** If `workflow.review_mode == "auto"` and `adapters.abtest.id` is `null`, stop with:

```
SETUP CHECK FAILED: auto mode with no abtest adapter
config.workflow.review_mode = "auto"
config.adapters.abtest.id = null
fix: either (a) set review_mode to "manual" or "off", or
            (b) author an abtest adapter via skills/author-adapter.md and set
                adapters.abtest.id to its filename.
setup stopped.
```

**c) Auto allocation must be live (hard).** If `workflow.review_mode == "auto"` and `workflow.auto_allocation_pct < 1`, stop with:

```
SETUP CHECK FAILED: auto mode with 0% allocation
config.workflow.review_mode = "auto"
config.workflow.auto_allocation_pct = <value>
fix: auto mode pushes tests live. Set auto_allocation_pct to the
     traffic % you want the test to run at (default 50 = even split
     with control). If you want the 0% staging flow where the human
     ramps traffic manually, use review_mode: "manual" instead.
setup stopped.
```

**d) Test-window floor (warning + clamp).** Compute `test_window_hours = test_window.value * (24 | 168 | 730)`. If `test_window_hours < outer_loop.min_experiment_hours`, warn and clamp upward:

```
WARNING: workflow.test_window resolves to <Nh>, which is below the
outer_loop.min_experiment_hours floor (<Mh>). Clamping test_window
to <Mh>. Either raise workflow.test_window or lower
outer_loop.min_experiment_hours to silence this warning.
```

**e) Abtest adapter must accept `allocation_pct` (hard in auto mode, warning in manual).** Parse the abtest adapter file and confirm its `## write :: push_variant` section accepts an `allocation_pct` argument per `adapters/README.md`. If the adapter hardcodes the allocation:
- `review_mode == "auto"` → stop with "adapter does not accept allocation_pct; auto mode cannot honor auto_allocation_pct". Set the fix hint to "upgrade the adapter to take allocation_pct, or switch to manual mode".
- Otherwise → warn but continue; in manual mode all pushes are 0% and the hardcoded adapter will still work.

**f) Auto-apply warning (advisory).** If `workflow.auto_apply_to_repo == true`, print:

```
WARNING: workflow.auto_apply_to_repo is true.
The agent will commit patches directly to <config.project.root> without
human review of each patch. Ensure:
  - config.guardrails.deny_globs covers all sensitive paths.
  - config.workflow.auto_apply_threshold (<value>) is high enough.
  - config.git.use_branch is set to your preferred branch strategy.
Proceed only if you have reviewed these settings.
```

**g) Phase 2/3 prevalidation helpers must exist (hard).** If `prevalidation.lighthouse.enabled == true`, confirm `harness/lighthouse.sh` and `harness/apply-patch.sh` exist. If `prevalidation.persona.enabled == true`, confirm `harness/persona-sim.md` and the configured `prevalidation.persona.personas_file` exist. Missing any of these stops setup with:

```
SETUP CHECK FAILED: Phase 2/3 prevalidation helper not shipped
enabled flag: prevalidation.<lighthouse|persona>.enabled = true
missing file: <path>
fix: these helpers are opt-in and not yet shipped with the framework.
     Either (a) set the matching prevalidation.<phase>.enabled flag to
     false, or (b) author the helper yourself. The MVP runs zero-dep
     with llm_judge + heuristic signals only.
setup stopped.
```

**h) Schedule echo.** If `schedule.enabled == true`, echo the schedule back to the human as confirmation:

```
schedule: enabled — will prompt for cron setup (every <interval_value> <interval_unit>).
```

Schema already enforces the valid value ranges; the echo is purely for human visibility.

**i) Cadence pattern check (advisory).** If `config.workflow.cadence` is set, echo the chosen pattern and verify the underlying config bundle matches the recommended values from README.md "Cadence patterns". This is purely a sanity warning — it never blocks the run. The cadence field documents intent; the actual behavior comes from `review_mode`, `auto_apply_to_repo`, `schedule.enabled`, and `budget.max_variants_per_run`.

Recommended bundles per cadence:

| cadence | review_mode | auto_apply_to_repo | schedule.enabled | max_variants_per_run |
|---------|-------------|--------------------|-----------------|----------------------|
| `weekly_batch` | `manual` | `false` | `false` | ~20 |
| `on_demand` | `manual` or `auto` | `false` | `false` | ~10 |
| `scheduled_cron` | `auto` | `true` | `true` | ~30 |

For each setting that diverges from the recommended bundle for the chosen cadence, print a single warning line:

```
WARNING: workflow.cadence = "<value>" expects <key> = <recommended>, but got <actual>.
This is a sanity warning — your run will proceed unchanged. Either update <key> to
match the cadence recommendation, or change workflow.cadence to a pattern that fits
your settings.
```

If `workflow.cadence` is absent, no warning — the field is optional and defaults to "on_demand" semantics. Document the inferred default in `run.log`.

### 8. Confirm success

If all steps pass, write one line to `run.log`:

```
{"ts": "<ISO-8601>", "event": "setup_check_passed", "adapter": null, "capability": null, "files_read": <n>, "files_written": 1, "notes": "config.yaml and all enabled adapters validated"}
```

And tell the human:

```
setup-check passed: config.yaml OK, adapters validated ({n_adapters} enabled, {n_null} null), env vars set.
```

Then return control to `program.md` for the remaining setup steps.

## What this skill must NOT do

- **Do not edit `config.yaml`.** If a value is wrong, the human fixes it — the skill only reports.
- **Do not prompt the human for missing env vars.** Stop with an actionable error and let the human set them before re-running.
- **Do not guess at adapter ids.** If the file is missing, say so; don't silently fall back.
- **Do not skip a step on exit code 4.** Exit 4 is a helper crash; log a warning but flag the config as unvalidated — do not continue as if nothing happened.
- **Do not run the inner loop.** This skill is pure validation. `program.md` handles loop orchestration.

## Fixture mode note

When `config.mode: fixture`:

- Step 5 (env var check) is skipped — fixture adapters don't need credentials.
- Step 6 (validate-adapter) runs each capability against the fixture file's pre-shaped data via the adapter's `## fallbacks` `mode: fixture` branch. This proves both the adapter AND the fixture agree on the normalized shape, which is the whole point of fixture-mode validation.

If fixture mode fails validation, the bug is almost always in the adapter's `## read` section, the fixture sample file, or the schema — in that order.
