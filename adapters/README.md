# Adapters

Adapters are **markdown playbooks** the agent reads and executes inline via its normal tool-calling (curl, bash, git, file read/write, optional MCPs). They are NOT runtime code. A full adapter is typically 50–150 lines of markdown.

The framework ships **two kinds** of adapters:

- **Reference adapters** for the common tools. You can use them directly by setting `adapters.<kind>.id` to their ID in `config.yaml` and exporting the env vars they declare in `## requires`. These live at `adapters/<kind>/<id>.md` and are covered by the mechanical contract validator (`harness/validate.py`) in CI.
- **Structural examples** (`null` and `fixture`) that every kind ships. `null` is a safe no-op; `fixture` reads from `fixtures/<kind>-sample.json` for offline verification and smoke tests.

If your tool isn't in the reference list, author your own via `skills/author-adapter.md` — an interactive flow that copies `TEMPLATE.md`, walks you through every section, runs the `## health` checks, runs `skills/validate-adapter.md` against the new adapter to confirm it returns the contracted shapes, and updates `config.yaml`.

## What ships

```
adapters/
  README.md              <- you are here
  TEMPLATE.md            <- the blank contract; copy this to create a new adapter

  analytics/
    null.md              <- no-op; returns empty reads
    fixture.md           <- reads fixtures/analytics-sample.json
    ga4.md               <- REFERENCE: Google Analytics 4 (service-account auth)
    plausible.md         <- REFERENCE: Plausible (API key, simple)
    posthog.md           <- REFERENCE: PostHog (HogQL queries)

  heatmap/
    null.md
    fixture.md           <- reads fixtures/heatmap-sample.json
    clarity.md           <- REFERENCE: Microsoft Clarity (Data Export API)
    posthog.md           <- REFERENCE: PostHog (autocapture + session recordings metadata)

  abtest/
    null.md              <- "plan only" mode: writes experiment.json with status=plan_only
    fixture.md           <- simulates a completed experiment for verification
    growthbook.md        <- REFERENCE: GrowthBook (open source, feature-flag based)
    posthog.md           <- REFERENCE: PostHog Experiments product
```

Reference adapters use env-var-only configuration — the repo contains zero credentials, zero property IDs, and zero tenant-specific config. You set env vars in your shell before running the inner loop; the adapter reads them at call time via the `*_env` convention.

## The three kinds

- **analytics** — reads session / conversion / funnel data. Required for meaningful hypotheses; without it the inner loop has no data to ground itself in.
- **heatmap** — reads attention / click / rage-click / session data. Optional but adds a lot of signal to hypotheses.
- **abtest** — pushes variants as real experiments AND reads their results once they reach significance. Optional. When `adapters.abtest.id: null` the framework runs in "plan only" mode: the inner loop still generates and pre-validates variants, but nothing is pushed anywhere.

## The contract

Every adapter must implement this contract. Fields in parentheses are optional.

```markdown
# Adapter: <human name>
kind: analytics | heatmap | abtest
id: <unique id used in config, lowercase kebab-case>
requires:
  env: [ENV_VAR_NAME_1, ENV_VAR_NAME_2]   # API keys / tokens, env-only
  command: [curl, jq, other-cli]          # CLI tools that must be on PATH
  mcp: [name-of-mcp-if-any]               # (optional) MCP tools this adapter uses

## health
...

## capabilities
...

## read
...

## write                  (abtest adapters only)
...

## idioms
...

## fallbacks
...
```

### `## health`

A checklist of read-only operations that must succeed before the loop trusts the adapter. At setup, `program.md` runs this for every enabled adapter. A required adapter that fails health → setup stops. Structure as a numbered list; each step is a concrete call and a pass criterion:

```
1. `curl -sS "$BASE_URL/ping" -H "Authorization: Bearer $TOKEN"` → expect HTTP 200 and JSON body `{"status": "ok"}`.
2. List properties. Expect at least one property matching `config.adapters.<id>.property_id`.
3. Fetch top pages for the last 7 days, limit 5. Expect a non-empty result.
```

### `## capabilities`

List the contract methods this adapter implements. Adapters do not have to implement every capability for their kind — mark unsupported ones explicitly so the inner loop routes around them.

```
- top_pages:       implemented
- landing_pages:   implemented
- funnel:          not_implemented (tool does not expose funnel API)
- traffic_sources: implemented
- conversions:     implemented
- session_quality: not_implemented
```

### `## read`

For each implemented capability, show:

1. The exact call (curl command, CLI invocation, MCP tool call, etc).
2. Any transformation to normalize the response.
3. The **normalized return shape** matching the contract below.

```
### top_pages(window="28d", limit=25)
Call:
    curl -sS "$BASE_URL/reports/top-pages?window=$window&limit=$limit" \
         -H "Authorization: Bearer $TOKEN" | jq '.data'
Transform: rename `page_url` -> `path`, `event_count` / `session_count` -> `conv_rate`.
Return:
    [{"path": "/pricing", "sessions": 12340, "bounce_rate": 0.61,
      "conv_rate": 0.018, "avg_time_s": 42}, ...]
```

### `## write` (abtest adapters only)

Exact steps to push a variant, get the experiment ID, and get results once it's ready.

```
### push_variant(slug, patch_path, description, allocation_pct)
1. Validate allocation_pct is an integer in [0, 100]. 0 is the staging default
   used in manual mode; values >= 1 mean the test goes live at that split
   percentage. Reject anything outside [0, 100] with a clear error.
2. POST /experiments with body {name: slug, description,
     allocation: allocation_pct / 100.0, ...}.
3. Attach the patch: POST /experiments/:id/attachments with patch_path.
4. Return {experiment_id, adapter: <id>, allocation: allocation_pct / 100.0,
     started_at}.

### get_experiment(experiment_id)
GET /experiments/:id/results -> {visitors, lift, ci_low, ci_high, p, status}.
```

Every abtest adapter's `push_variant` MUST accept `allocation_pct` as a required argument. Adapters that hardcode 0% staging are considered broken; setup-check will refuse to run with `review_mode: "auto"` against such an adapter. In `review_mode: "manual"` and `review_mode: "off"` the caller always passes `allocation_pct=0`, so legacy hardcoded adapters will still work but will warn.

### `## idioms`

Short rules for interpreting the data. Examples:

- "Sampling kicks in above 1M events/day — report counts become estimates."
- "Timestamps are UTC but the dashboard shows account-local time."
- "Data lags real-time by ~30 minutes."
- "Funnel steps are ordered lexicographically unless you set `step_order`."

These are used by `skills/hypothesize.md` to avoid misinterpretation.

### `## fallbacks`

What to do when the adapter call fails. Must explicitly cover:

- HTTP 5xx → retry once with smaller window, then log warning and return empty.
- HTTP 4xx auth → stop immediately with a clear "credentials invalid" error.
- Quota / rate limit → back off, retry once, then return empty.
- **`mode: fixture`** → bypass the live call entirely and read from `fixtures/{kind}-sample.json` with no network. This is required for verification to work offline.

## Normalized return shapes (the contract)

`skills/hypothesize.md` is adapter-blind — it reads the shapes below regardless of which tool is on the other end. Every `## read` must return one of these shapes (or an empty array / object on no data).

### analytics

```jsonc
// top_pages(window, limit)
[{"path": "/pricing", "sessions": 12340, "bounce_rate": 0.61,
  "conv_rate": 0.018, "avg_time_s": 42}, ...]

// landing_pages(window, limit)
[{"path": "/pricing", "landings": 8420, "bounce_rate": 0.68,
  "conv_rate": 0.012}, ...]

// funnel(steps)
[{"step": "landing", "entered": 10000, "advanced": 6200},
 {"step": "form",    "entered":  6200, "advanced":  980},
 {"step": "submit",  "entered":   980, "advanced":  410}]

// traffic_sources(window, limit)
[{"source": "google.com", "medium": "organic", "sessions": 5200,
  "conv_rate": 0.021}, ...]

// conversions(event, window)
{"event": "sign_up", "count": 410, "sessions": 12340, "rate": 0.0332}

// session_quality(path, window)
{"path": "/pricing", "avg_time_s": 42, "scroll_depth_p50": 0.48,
 "bounce_rate": 0.61, "engagement_score": 0.33}
```

### heatmap

```jsonc
// page_attention(path)
{"path": "/pricing", "scroll_depth_p50": 0.42, "scroll_depth_p90": 0.78,
 "hotspots": [{"selector": ".cta-primary", "intensity": 0.83}, ...]}

// click_map(path, limit)
[{"selector": ".cta-primary", "clicks": 1240, "rage_click_rate": 0.02},
 {"selector": "nav a[href='/pricing']", "clicks": 980, "rage_click_rate": 0.0},
 ...]

// rage_clicks(path, limit)
[{"selector": ".disabled-submit", "count": 62,
  "sample_note": "users clicking a disabled button"}, ...]

// session_sample(path, n)
[{"session_id": "s_abc", "duration_s": 124, "events": 47,
  "goal_reached": false, "notable": "rage click on pricing FAQ"}, ...]
```

### abtest

```jsonc
// push_variant(slug, patch_path, description, allocation_pct) -> returns:
// allocation_pct is an integer in [0, 100]; the adapter converts to its
// own internal representation. Manual mode always passes 0; auto mode
// passes config.workflow.auto_allocation_pct (default 50).
// `allocation_pct` MAY be echoed back in the response so validate-adapter.md
// can assert round-trip; it is optional per the schema but recommended.
{"experiment_id": "<adapter-defined>", "adapter": "<adapter id>",
 "allocation": 0.5, "allocation_pct": 50, "started_at": "<ISO-8601>"}

// get_experiment(experiment_id) -> returns:
{"experiment_id": "<id>", "status": "running|completed|stopped",
 "visitors": 4200, "lift": 0.037,
 "ci_low": 0.012, "ci_high": 0.061, "p": 0.032,
 "started_at": "<ISO-8601>", "ended_at": "<ISO-8601 | null>"}

// list_experiments() -> returns:
[{"experiment_id": "...", "name": "...", "status": "running", "lift": 0.01},
 ...]

// promote(experiment_id, allocation) -> returns:
{"experiment_id": "...", "allocation": 0.5}
```

## Authoring a new adapter

The easiest path is `skills/author-adapter.md` — an interactive flow that walks you through copying `TEMPLATE.md`, filling in every section based on your answers and your tool's docs, running the `## health` check, and updating `config.yaml`. Prompt Claude:

> Read `autocro/skills/author-adapter.md` and help me author an analytics adapter. I use `<your tool>`; docs are at `<url>`.

Or manually:

1. `cp adapters/TEMPLATE.md adapters/<kind>/<your-tool-id>.md`
2. Fill in every section, following the patterns in the `null` and `fixture` adapters as structural references.
3. Reference credentials only via `requires.env` names — never inline.
4. Ensure every implemented capability's `## read` returns the normalized shape exactly.
5. Set `adapters.<kind>.id: <your-tool-id>` in `config.yaml`.
6. Run program.md setup — it will execute the adapter's `## health` section before proceeding.

## Reference adapter requirements

A reference adapter MAY be checked into this framework at `adapters/<kind>/<id>.md` if and only if it meets ALL of these requirements:

1. **Env-var-only configuration.** Every credential, account ID, property ID, base URL override, etc. is referenced via an env var name (`*_env` in `## requires`). The adapter file itself contains no tenant-specific values.
2. **`mode: fixture` fallback.** The `## fallbacks` section must handle `mode: fixture` by reading from `fixtures/<kind>-sample.json` and demultiplexing to the per-capability normalized shape. This is how validation runs without burning real API quota.
3. **Passes `skills/validate-adapter.md` in fixture mode.** Every capability marked `implemented` must return JSON matching `harness/schemas/<kind>.json` exactly. No stray keys, no renamed fields, no type mismatches.
4. **`Last verified: YYYY-MM` date** in `## idioms`. Upstream APIs evolve; reference adapters are snapshots. The date tells users when it was last exercised against the real tool.

Per-project adapters (anything with an account-specific value, or anything the user customizes) stay in the user's parent repo and should not be committed to the framework. `skills/author-adapter.md` writes per-project adapters to the right place by default.

## Do not

- Do not embed API keys, property IDs, or tenant-specific values in reference adapter markdown, fixtures, or config.
- Do not skip the `## fallbacks` section, especially `mode: fixture` handling — verification depends on it.
- Do not write code adapters. Adapters are markdown playbooks. If a tool's API is too complex for markdown to describe (e.g. needs JWT signing, complex pagination), write a tiny stdlib-only helper in `harness/` and have the adapter invoke it via `python3`.
- Do not overwrite a shipped reference adapter with customizations. Copy it to a new filename (e.g. `ga4-internal.md`) and edit the copy. Reference adapters are upgraded when the framework updates; in-place customizations would be clobbered.
