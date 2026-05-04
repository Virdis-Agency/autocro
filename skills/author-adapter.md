# Skill: author-adapter

Interactively create a new adapter markdown playbook for whatever tool the parent project uses. You (the agent) walk the human through it, copy `adapters/TEMPLATE.md` to the new path, fill in every section, run the `## health` check, and update `config.yaml`.

This is the skill users run first when they drop `autocro/` into a new project. No tool-specific knowledge is baked into the framework — every integration is authored per project via this skill.

## When to run

- Explicitly requested by the human ("author a new adapter for X").
- Automatically, from `program.md` setup step, when all three adapters in `config.yaml` are `null` and `mode` is not `fixture`. In that case, run once per kind (analytics, heatmap, abtest), asking the human which tool they use or whether to leave it as `null` for now.

## Interactive flow

Ask the human each question in turn. Wait for an answer before the next question. Do NOT assume.

### 1. Which kind?

> Which kind of adapter are we authoring?
> - analytics (e.g. page views, funnels, conversions)
> - heatmap (e.g. scroll depth, click density, rage clicks, session recordings)
> - abtest (e.g. feature flags, experiments, traffic allocation)

### 2. Which tool?

> What tool do you use for this?

Whatever the human says, use it to derive a kebab-case ID:

- "PostHog" → `posthog`
- "Microsoft Clarity" → `clarity`
- "My homegrown analytics" → `homegrown` (or ask)
- "We use two: Mixpanel for events and Amplitude for funnels" → ask which one they want the adapter to call, or author two adapters

### 3. How does the agent talk to it?

> How should the agent access this tool's data? Check all that apply:
> - REST API (provide the base URL and docs link)
> - CLI tool installed on this machine (provide the command name)
> - SDK for a specific language (which language, which package?)
> - MCP server already configured in this Claude Code session (provide the tool name prefix if you know it)
> - Webhook / file drop / other

### 4. Authentication

> How does the tool authenticate requests? (API key in header / bearer token / OAuth / no auth / other)
> If credentials are needed, what environment variable name should I reference? (e.g. MYTOOL_API_KEY — I will never inline the actual key)

Validate that the proposed env var follows the `*_KEY` / `*_TOKEN` / `*_SECRET` convention. Never ask for the actual secret value — only the env var name.

### 5. Capabilities

> Which of the contract capabilities does this tool support? For the ones you don't know, I can check the docs in a minute.

For **analytics** adapters, ask about: `top_pages`, `landing_pages`, `funnel`, `traffic_sources`, `conversions`, `session_quality`.
For **heatmap** adapters, ask about: `page_attention`, `click_map`, `rage_clicks`, `session_sample`.
For **abtest** adapters, ask about: `push_variant`, `get_experiment`, `list_experiments`, `promote`, `archive`.

Adapters do not need to implement every capability. Mark unsupported ones in the adapter's `## capabilities` section so the inner loop can route around them.

### 6. Example payloads

> Can you paste an example API response for each capability you want to support? Or point me at docs I can fetch (use `WebFetch`).

This is the most important step. Without real example payloads, you will write an adapter that returns the wrong shape. The inner loop relies on the **normalized shapes** defined in `adapters/README.md`, and the `## read` section of your adapter must translate the raw tool response to the normalized shape.

### 7. Idioms and caveats

> Are there any gotchas with this tool? For example:
> - Sampling at high volume?
> - Rate limits?
> - Time zone quirks?
> - Data freshness lag?
> - Minimum sample size before results are meaningful?

Capture these in the `## idioms` section — they shape how `skills/hypothesize.md` interprets the data.

## Authoring the file

1. **Copy the template**:
   ```
   cp adapters/TEMPLATE.md adapters/{kind}/{id}.md
   ```

2. **Fill in the front matter**: `id`, `kind`, `requires` (env vars, commands, MCP tools as applicable).

3. **Fill in `## health`**: a sequence of read-only calls that prove the adapter is working. For an analytics adapter, typically: list the property IDs, fetch top pages with a 7-day window, check the result is non-empty. Each health step is a concrete call (curl command, MCP invocation, etc.) with a pass criterion.

4. **Fill in `## capabilities`**: list the methods you implemented.

5. **Fill in `## read`** (and `## write` for abtest): for each capability, show the exact call the agent should make and the return shape that matches the normalized contract in `adapters/README.md`. If the raw tool response needs transformation, include a short transformation step (e.g. "map `page_url` to `path`, divide `events_count` by `sessions` for `conv_rate`").

6. **Fill in `## idioms`**: the caveats from step 7.

7. **Fill in `## fallbacks`**: what to do on HTTP errors, quota limits, auth failures. Must handle `mode: fixture` by reading from `fixtures/{kind}-sample.json` with no live call.

## Validation

Once the file is written:

1. **Run the `## health` section.** Walk through each step and report pass/fail to the human. If any step fails, go back to the relevant section of the adapter and fix it.

2. **Run one `read` capability end-to-end.** Pick the simplest capability (usually `top_pages` or equivalent) and actually call the tool. Show the human the normalized response. Confirm it matches the expected shape from `adapters/README.md`.

3. **Run `skills/validate-adapter.md` against the new adapter** in the current `config.mode`. This invokes `harness/validate.py` against every implemented capability's response and verifies it matches `harness/schemas/<kind>.json`. If any capability fails:
   - Show the human the full validator error block verbatim (it names the exact wrong key, the expected shape, and the fix).
   - Go back to the adapter's `## read` section for the failing capability and add or fix the `Transform:` step so the raw tool response is re-shaped to match the normalized contract.
   - Re-run validate-adapter. Iterate until every implemented capability passes.
   - **DO NOT proceed to step 4 until validation passes.** A broken adapter committed to the project silently corrupts hypothesis sourcing in the inner loop.
   - If a capability genuinely cannot be implemented against the tool (e.g. the API doesn't expose funnels), mark it `not_implemented` in the adapter's `## capabilities` section instead of faking a response shape. `skills/validate-adapter.md` will skip `not_implemented` capabilities.

4. **Update `config.yaml`**: set `adapters.{kind}.id` to the new adapter's ID. If the adapter has per-adapter config (property IDs, base URLs, env var names), add a config block under `adapters.{id}:`. Show the human the diff and ask them to confirm before writing.

5. **Commit message suggestion**: tell the human they may want to commit the new adapter file to their repo (but NOT `config.yaml` since it may contain property IDs they'd rather keep out of git). Do not commit for them.

## Safety rules

- **Never inline a real credential** in any file. Only environment variable names.
- **Never ask the human to paste a secret value.** Only ask for the env var name.
- **Never guess** a tool's API behavior. If you don't have docs or an example response, use `WebFetch` to read the official docs, or ask the human to paste an example.
- **Never mark an adapter as complete** unless `## health` AND `skills/validate-adapter.md` both pass end-to-end. A broken adapter in the loop silently corrupts hypothesis sourcing.
- **Never overwrite a reference adapter.** The framework ships reference adapters at `adapters/<kind>/<id>.md` (e.g. `adapters/analytics/ga4.md`, `adapters/abtest/growthbook.md`). If the human wants to customize a reference adapter, copy it to a new filename (e.g. `ga4-custom.md`) and edit the copy. Do NOT overwrite the shipped file — that would create a merge conflict the next time the framework is updated.
- **Per-project adapters stay in the user's repo.** Unless the human is explicitly contributing a new reference adapter upstream (and it meets the requirements in `adapters/README.md`: env-var-only config, fixture fallback, passes validator), adapters authored by this skill live in the user's parent project, not in the framework.

## When the human says "just use fixture mode for now"

Skip all of the above. Set `mode: fixture` in `config.yaml` and all three `adapters.*.id: fixture`. Confirm the fixture files exist under `autocro/fixtures/`. The inner loop will run against canned data — useful for evaluating the framework before wiring up real tools.
