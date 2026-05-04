# Skill: validate-adapter

Given an adapter file path and the current `config.mode`, exercise each capability the adapter claims as `implemented` and verify the returned JSON matches the normalized contract in `harness/schemas/<kind>.json`. On any failure, surface a line-addressed, actionable error that names the adapter file, the capability, the exact wrong key, and how to fix the adapter's `## read` section.

Invoked by `skills/setup-check.md` step 6 (setup-time gating) and by `skills/author-adapter.md` (post-authoring verification). Calls `harness/validate.py`.

## Why this exists

Today's adapter contract is enforced by prose in `adapters/README.md:138-210`. Without this skill, a wrong-shape adapter (e.g. returns `{"page": "/x"}` instead of `{"path": "/x"}`) would silently break `skills/hypothesize.md` hours into the inner loop — the human would see weird output and have no clue why. With this skill in place, the error surfaces in <1 second at setup time, with a clear fix.

## Inputs

- `adapter_path` — e.g. `autocro/adapters/analytics/ga4.md`
- `config.mode` — `live` or `fixture`
- Optionally: a list of capabilities to validate (defaults to all capabilities the adapter marks `implemented`)

## Steps

### 1. Parse the adapter's `## capabilities` section

Read the adapter file and find the `## capabilities` block. Collect every entry whose status is `implemented`. Capability names must match the keys in `harness/schemas/<kind>.json` `$defs/` exactly (e.g. `top_pages`, not `top pages` or `topPages`).

If the `## capabilities` block is missing or malformed, stop with:

```
VALIDATION FAILED: <adapter_path>
problem: adapter has no parseable ## capabilities section
fix: add a ## capabilities section listing each capability as "<name>: implemented" or "<name>: not_implemented".
setup stopped.
```

### 2. For each implemented capability, invoke the adapter's `## read` call

Follow the adapter's `## read` section for that capability. Use the current mode:

- `mode: live` → execute the real API call as documented (curl, CLI, MCP, etc.). Use the `requires.env` vars already verified by `setup-check.md`.
- `mode: fixture` → follow the `## fallbacks :: mode: fixture` branch, which reads from `fixtures/<kind>-sample.json` and demultiplexes to the per-path or per-capability slice the contract expects.

For heatmap `click_map`, `rage_clicks`, and `session_sample`, the fixture file is multiplexed by path — extract the slice for one of `config.goal.target_paths` (use the first one that exists in the fixture, typically `/signup`).

Write the response to stdout as JSON.

### 3. Pipe the response through `harness/validate.py`

```bash
python3 autocro/harness/validate.py <kind> <capability> --stdin < adapter_response.json
```

Where `<kind>` is `analytics | heatmap | abtest` and `<capability>` is the capability name from step 1.

The validator exits with:

- **0** → the response matches the schema. Continue to the next capability.
- **2** → validation failure. Capture stderr verbatim and continue validating the remaining capabilities, then aggregate into a single error report in step 4.
- **3** → schema or input load failure. Usually means a typo in the capability name or the adapter returned malformed JSON. Stop immediately with the validator's error.
- **4** → validator helper crashed. Log a warning to `run.log` with the full stderr and exit 4 to the caller. setup-check.md treats exit 4 as "degraded mode, continue with warning" — the caller decides what to do.

### 4. Aggregate failures and report

If every capability passed, write one line to `run.log`:

```
{"ts": "<ISO-8601>", "event": "adapter_validate_pass", "adapter": "<adapter_id>", "capability": null, "files_read": <n>, "files_written": 1, "notes": "<n_caps> capabilities validated"}
```

and tell the caller `validate-adapter passed for <adapter_path> (<n_caps>/<n_caps> capabilities)`.

If any capability failed, stop with a single aggregated error block:

```
VALIDATION FAILED: <adapter_path>
mode: <live|fixture>
failed capabilities: <list>

<first validator stderr block, verbatim>

<second validator stderr block, verbatim>

...

fix: edit <adapter_path> under the "## read" section for the listed capabilities.
     For each one, check that the Transform step in the adapter maps the raw
     tool response to the exact normalized shape in harness/schemas/<kind>.json.
     The most common bugs are:
       - key renames (tool says "page", contract says "path")
       - wrong types (string instead of number, or vice versa)
       - missing required keys (contract requires them even if zero-filled)
       - stray keys the contract forbids (additionalProperties: false)
     If a capability genuinely cannot be implemented against this tool, mark
     it "not_implemented" in the adapter's ## capabilities section instead
     of trying to fake a response shape.
setup stopped.
```

## Mode-specific notes

### `mode: fixture`

- Every reference adapter ships with a `mode: fixture` fallback in its `## fallbacks` section. That fallback reads from `fixtures/<kind>-sample.json` and slices it to the per-capability shape. The agent follows those instructions literally — no live API calls, no env vars required.
- This is the only form of validation `skills/setup-check.md` runs by default, because running full live-mode validation at every setup can burn API quota on rate-limited tools (e.g. Microsoft Clarity's 3 req/day free tier).
- If live validation is explicitly requested (e.g. immediately after `skills/author-adapter.md` to prove the new adapter actually talks to the real tool), it runs once with a small window (`window=7d`, `limit=5`) to minimize quota burn.

### `mode: live`

- Use the real API call from the adapter's `## read` section. Use small windows and low limits — validation is a "does the shape match", not a "fetch useful data" step.
- If rate limits hit, back off and retry once with an even smaller window. Second failure → report as a capability failure and move on.
- Treat 4xx auth failures as a hard stop with "credentials invalid" error, not a validation failure — that's a setup-check problem, not a shape problem.

## Do not

- **Do not modify the adapter file** to make validation pass. If the shape is wrong, the human fixes it.
- **Do not cache validation results.** Every setup invocation runs validation fresh. Adapters can go bad silently between runs (upstream API changes), and caching would hide that.
- **Do not skip capabilities listed as `implemented`.** The whole point is that `implemented` is a promise — if the capability is flaky, mark it `not_implemented` instead.
- **Do not run during the inner loop.** Validation is strictly a setup-time check (and a one-shot check after adapter authoring). The inner loop trusts the adapters once setup-check passes.
