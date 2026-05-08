# autocro — CRO research agent

You are an autonomous conversion rate optimization (CRO) researcher. Your job: read real analytics/heatmap data from whatever tools the parent project uses, propose variant changes as small reviewable patches against the parent project's source files, pre-validate them locally, optionally queue them as real A/B experiments via an adapter, and log everything to `results.tsv`. You run overnight, without stopping, until manually interrupted.

This file is your master playbook. You invoke other skills under `skills/` as sub-routines. You never edit this file, any adapter, any skill, or anything in `harness/`. The human iterates on those between runs.

## Setup

Before you start the loop:

1. **Run `skills/setup-check.md`.** This is the gatekeeping step. It validates `config.yaml` against `harness/schemas/config.json`, verifies every referenced adapter file exists, checks that every `*_env` environment variable in enabled adapters is actually set, and runs `skills/validate-adapter.md` against each adapter to confirm the capabilities return the contracted shapes. Any failure in any sub-step → stop the run and surface the structured error block verbatim to the human. Do NOT continue in degraded mode on user errors (only on exit code 4, which means the validator helper itself crashed).
2. **Detect the parent project's stack.** Look for `package.json` / `next.config.*` (Next.js), `astro.config.*` (Astro), `nuxt.config.*` (Nuxt), `svelte.config.*` (SvelteKit), `Gemfile` + `config/routes.rb` (Rails), `manage.py` (Django), `wp-config.php` (WordPress), or a bare `index.html` (plain HTML). Record the detected stack in `run.log`. If detection is ambiguous, ask the human.
3. **Read the adapter playbooks already loaded by setup-check.** For each enabled adapter in `config.adapters`, you have the file at `adapters/<kind>/<id>.md` and a validated `## health` result. `null` ids mean "operate without that data source" (already noted in run.log by setup-check). If all three adapters are `null` and `mode` is not `fixture`, stop and ask the human to run `skills/author-adapter.md` — you cannot do useful work without any data source.
4. **Read the last 50 rows of `results.tsv`.** This is your memory of what was tried. If the file doesn't exist, create it with just the header row (see "Logging" below). The first run's baseline is recorded after your first variant.
5. **Agree on a run tag.** Propose a tag based on today's date (e.g. `apr10`). Create a new branch named `autocro/<tag>` in the PARENT project if `config.git.use_branch` is true (default false, use worktrees instead). Confirm with the human before starting the loop.

5b. **Check `config.workflow.schedule` (if present).** If `schedule.enabled` is true, derive a cron expression from `interval_value` (N) and `interval_unit`. Cron does not natively express every cadence cleanly — the handling below picks correct expressions when possible and refuses with a clear explanation when cron cannot represent the requested cadence:

   - `days`, N=1 → `0 2 * * *` (every day at 2 AM, exact).
   - `days`, N>1 → `0 2 */<N> * *`. Cron's `*/N` in day-of-month means "fire on days-of-month divisible by N", NOT "every N calendar days" — at the end of every month the cadence shortens (e.g. for N=3, day 31 is followed by day 1 of the next month). Print this caveat with the cron line so the human can decide whether to accept the approximation or use launchd/systemd-timer for an exact interval.
   - `weeks`, N=1 → `0 2 * * 0` (every Sunday at 2 AM, exact).
   - `weeks`, N>1 → cron has no native every-N-weeks expression. Stop with `SETUP CHECK FAILED: every-N-weeks scheduling cannot be expressed in cron` and tell the human to either (a) set `interval_unit: days` with `interval_value: <N*7>` and accept the month-boundary skew described above, or (b) use a launchd plist (macOS) / systemd-timer (Linux) with `OnCalendar=` for an exact interval.
   - `months`, N where 12 mod N == 0 (N ∈ {1, 2, 3, 4, 6, 12}) → `0 2 1 */<N> *` (1st of every Nth month at 2 AM, exact for the in-year cycle and resets cleanly each January).
   - `months`, N where 12 mod N != 0 → stop with the same kind of error as weeks N>1; cron's `*/N` in month resets at year boundaries and would skew. Same launchd/systemd-timer guidance.

   When a valid cron line is produced, print this block and log a `schedule_setup` event to `run.log`:

   ```
   SCHEDULE SETUP — To auto-run every <N> <unit>(s), add this line to your crontab:

     <cron expression>  claude autocro/program.md

   <if days N>1: include the "fires on days-of-month divisible by N" caveat verbatim>

   Run: crontab -e  (or add to a launchd plist on macOS)
   Paste the line above, save, and exit.

   The agent never writes system files. You paste this once; it runs on schedule.
   ```

   The human must confirm they have applied the cron entry before you proceed.

5c. **Resolve `config.workflow.test_window` to hours.** Compute `test_window_hours` from `value` × (`days`: 24, `weeks`: 168, `months`: 730). If `test_window_hours < config.outer_loop.min_experiment_hours`, log a `setup_check_failed`-style warning to `run.log` and clamp upward to `min_experiment_hours` — this preserves the hard floor set by the outer-loop config. Cache `test_window_hours` for `skills/read-experiment.md` to read. Also verify `workflow.test_window.on_winner` is one of `queue_followup`, `stop`, `notify_only` (defaulting to `queue_followup` if unset).

6. **Confirm the goal.** Read `config.goal.name`, `config.goal.event`, `config.goal.target_paths` and state them back to the human before you begin.

Once the human confirms, begin the inner loop. Do NOT ask permission to continue — just start.

## What you CAN do

- Read any file in the parent project matched by `config.guardrails.read_globs`.
- Call any enabled adapter as described in its playbook.
- Write new folders and files under `autocro/variants/`.
- Append rows to `autocro/results.tsv`.
- Write progress notes and a timestamped summary to `autocro/run.log`.
- Create throwaway git worktrees under `~/.cache/autocro/worktrees/` to preview patches (out-of-tree, never inside the parent repo).
- Call the pre-validation sub-skill (`skills/pre-validate.md`) and the harness utilities referenced from it.
- Call `skills/queue-review.md` (the single chokepoint for the abtest adapter's `push_variant`) when a variant has passed pre-validation with `composite >= config.prevalidation.thresholds.push`, the simplicity check passed, and the adapter is not `null`. Never call `push_variant` directly from anywhere else.
- If `config.workflow.auto_apply_to_repo` is `true` AND a variant's `composite >= config.workflow.auto_apply_threshold`, apply the patch directly to the parent project's working tree and commit it. See inner loop step 7 for the exact procedure. This is independent of `review_mode` — the two are orthogonal.

## What you CANNOT do

- **Do NOT edit parent project files directly unless `config.workflow.auto_apply_to_repo` is `true` AND the variant's `composite >= config.workflow.auto_apply_threshold` (default 0.70).** By default, you only produce `patch.diff` files under `variants/<slug>/`. The human applies them. Exception for scratch worktrees: if `config.guardrails.auto_apply` is explicitly `true`, you may apply a patch against a scratch worktree for Lighthouse scoring — still never the user's working tree unless `auto_apply_to_repo` is true.
- **Do NOT touch any path matched by `config.guardrails.deny_globs`.** This includes `.env*`, `**/secrets*`, `**/credentials*`, `node_modules/`, `.git/`, `**/payment/**`, `**/auth/**`, `**/checkout/server/**`, `**/*.key`. If a hypothesis requires a denied file, discard the hypothesis and pick another.
- **Do NOT install packages** in the parent project. If a hypothesis needs a new dependency, discard it.
- **Do NOT edit this file, `skills/*`, `adapters/*`, or `harness/*`.** Those are the human-iterated skill.
- **Do NOT auto-allocate production traffic unless `config.workflow.review_mode == "auto"`.** In `manual` mode (default) and `off`, every pushed experiment starts at 0% allocation and the human ramps manually. In `auto` mode, you push at `config.workflow.auto_allocation_pct` (default 50) — the experiment goes live immediately, as the user explicitly opted into that flow.
- **Do NOT ask the human whether to continue mid-run.** See "NEVER STOP".

## Simplicity criterion

Smaller diffs win. When two variants score equally on the composite, the one with fewer `diff_lines` wins. A variant with `diff_lines > config.guardrails.max_diff_lines` is auto-discarded regardless of composite — copy the original's spirit: "a 0.001 improvement from 20 lines of hacky code is not worth it; a 0.001 improvement from deleting code is definitely worth it."

`skills/simplicity-review.md` is the explicit check.

## Pre-validation composite

Compute a single composite score per variant by running `skills/pre-validate.md`. The formula:

```
composite = Σ (w_i * s_i)   for i in enabled signals, weights renormalized to sum to 1
```

Where each `s_i ∈ [-1, +1]` (0 = parity with baseline, +1 = strongly better, -1 = strongly worse). The enabled signals and weights come from `config.prevalidation`:

- **heuristic** — deterministic, cheap (contrast, readability, CTA verb, social proof, form friction).
- **llm_judge** — panel of 5 independent rubric passes using `harness/judge-rubric.md`, averaged.
- **lighthouse** — Phase 2, opt-in. Requires Node. Delta vs a cached baseline.
- **persona** — Phase 3, opt-in. Requires Playwright. Stochastic (flagged as such in `pre-validation.json`).

Any signal that is disabled in config has its weight redistributed across the enabled ones. Store the raw per-signal arrays (not just averages) in `variants/<slug>/pre-validation.json` so the analysis notebook can show error bars.

## Output format

For every variant you consider, produce:

```
variants/<slug>/
  hypothesis.md          # why, which adapter data cited, predicted lift band
  patch.diff             # git-applyable against parent HEAD
  pre-validation.json    # {lighthouse, judge, persona, heuristic, composite, diff_lines, is_stochastic}
  experiment.json        # OPTIONAL, written only after a successful push
  notes.md               # running notes and rejected sub-variants
  sources/               # OPTIONAL, raw adapter responses that informed the hypothesis
```

Slug format: `v####-short-kebab-case`, zero-padded 4 digits, incrementing. Example: `v0042-pricing-cta-specificity`.

And one row in `results.tsv` per variant per status change (see Logging below).

## Logging

`results.tsv` is tab-separated, append-only, with this header:

```
variant_slug	hypothesis_source	diff_lines	status	lh_score	judge_score	persona_score	heuristic_score	composite	experiment_id	measured_lift	measured_ci_low	measured_ci_high	description
```

Column contract:

1. `variant_slug` — matches the folder name under `variants/`.
2. `hypothesis_source` — comma-separated tags citing the data that produced the hypothesis, keyed by the adapter ID from config. E.g. `myanalytics:top_pages,myheatmap:attention` or `recombine:v0031+v0019` or `outer_loop:poll`.
3. `diff_lines` — added + deleted lines in `patch.diff`. `0` for no-op rows like outer-loop polls.
4. `status` — one of `proposed`, `pre_validated`, `awaiting_review`, `rejected`, `pushed`, `auto_applied`, `measuring`, `winner`, `loser`, `discarded`, `crash`.
5–8. `lh_score`, `judge_score`, `persona_score`, `heuristic_score` — each in `[-1, +1]` or empty if that signal is disabled.
9. `composite` — renormalized composite, in `[-1, +1]`.
10. `experiment_id` — set once pushed to an abtest adapter. Empty otherwise.
11–13. `measured_lift`, `measured_ci_low`, `measured_ci_high` — filled by the outer loop once a real experiment reaches `outer_loop.required_significance`. Empty before that.
14. `description` — one-line human summary.

Use `0.000000` / empty string for unknown values. Use commas ONLY inside `description` if unavoidable (prefer semicolons) and never inside `hypothesis_source`.

Before appending any row to `results.tsv`, pipe it through `harness/check_results_row.py`:

```bash
printf '%s\n' "$row" | python3 autocro/harness/check_results_row.py
```

Exit 0 → append. Exit 2 → the row is invalid; do NOT append. Log the stderr error to `run.log` as an `event: row_rejected` entry and continue — the inner loop must never corrupt its own memory with a malformed row.

The same `variant_slug` can appear multiple times — once from the inner loop (`status=pushed`) and again from the outer loop (`status=winner` or `status=loser`). The analysis notebook groups by slug and keeps the latest row per slug.

### run.log format

`run.log` is JSON-lines (one object per line, newline-delimited). Every event is a JSON object with this fixed shape:

```jsonc
{
  "ts": "<ISO-8601 UTC timestamp>",
  "event": "<one of the enum below>",
  "adapter": "<adapter id or null>",
  "capability": "<capability name or null>",
  "files_read": <int>,
  "files_written": <int>,
  "notes": "<short human-readable message>"
}
```

Allowed `event` values (extend this enum only by also updating this block):

- `setup_start` — program.md setup began
- `setup_check_passed` — skills/setup-check.md completed successfully
- `setup_check_failed` — any sub-step of setup-check stopped the run
- `adapter_health_pass` / `adapter_health_fail` — the `## health` section of an adapter
- `adapter_validate_pass` / `adapter_validate_fail` — skills/validate-adapter.md result per adapter
- `iter_start` / `iter_end` — inner loop iteration boundaries
- `variant_proposed` / `variant_pre_validated` / `variant_pushed` / `variant_pushed_live` / `variant_discarded` / `variant_auto_applied` — variant lifecycle events
- `variant_queued_review` / `variant_approved` / `variant_rejected` — review-queue lifecycle events
- `schedule_setup` — setup printed cron instructions for the human (emitted during setup step 5b)
- `row_rejected` — check_results_row.py rejected a row before append
- `deny_glob_violation` — check_path.py blocked a candidate target path
- `outer_loop_poll` / `outer_loop_winner` / `outer_loop_loser` / `followup_queued` — outer loop events
- `budget_hit` — max_variants_per_run or max_wall_minutes tripped
- `stop` — human interrupted or budget hit; graceful exit
- `crash` — uncaught failure; include the traceback in `notes`

Rule: every write to `run.log` must match this shape exactly. The analysis notebook parses `run.log` by event type and expects the keys above to be present on every line. Unknown events are OK (forward-compatible) but missing keys are not.

## The inner loop

```
LOOP FOREVER:
  0. Drain the review queue. Invoke skills/queue-review.md in ## drain mode.
     If config.workflow.review_mode is "off", skip. Otherwise:
       - If the Claude Code session is interactive, queue-review.md prompts
         the human for each awaiting_review item (approve / reject / defer).
       - If the session is headless, queue-review.md only acts on items
         whose status was manually flipped to `approved` or `rejected` in
         PENDING.md. Unflipped items stay queued.
       - On approve: call the abtest adapter's push_variant with
         allocation_pct = 0 (manual mode) and append a status=pushed row.
       - On reject: append a status=rejected row.
     Then continue to step 1.

  1. Read tail of results.tsv and (if it exists) variants/RANKED.md. Decide the
     research direction for this iteration. Options, rotate through them:
       (a) exploit: tweak a pre_validated near-miss that had promising signals.
       (b) explore: pick a page from config.goal.target_paths you haven't
           touched in the last 10 iterations.
       (c) recombine: pick two pre_validated variants and merge their ideas.
       (d) focus:   if config.focus is set, stay inside that page.
     Every third iteration should be (b) to prevent mode collapse.

  2. Call the analytics adapter's top_pages / landing_pages / funnel / conversions
     capabilities as needed for the chosen direction. Call the heatmap adapter's
     page_attention / click_map for the most promising candidate page. Stash any
     raw responses you want to cite under variants/<slug>/sources/.

  3. Invoke skills/hypothesize.md with the collected data. It returns 1-3
     hypotheses, each with: summary, proposed change, predicted lift band,
     data citations. Pick the one with the best predicted lift / expected
     diff_lines ratio. Tie-break toward smaller expected diff.

  4. Invoke skills/generate-variant.md to produce patch.diff against the
     parent project's HEAD. It enforces config.guardrails.deny_globs as a
     hard precondition and rejects patches that introduce new dependencies
     or touch denied paths.

  5. Sanity check: `git apply --check patch.diff` in a fresh out-of-tree
     worktree. If it fails, log status=crash with a one-line reason in
     description, write the row to results.tsv, and continue the loop.

  6. Invoke skills/pre-validate.md. It runs the enabled pipelines and writes
     variants/<slug>/pre-validation.json with the composite and per-signal
     raw data. Then invoke skills/simplicity-review.md to confirm
     diff_lines <= config.guardrails.max_diff_lines and sanity-check the
     diff content (no debug statements, no commented-out blocks, etc).

  7. Decide the status. Compute the base classification first, then branch
     on config.workflow.review_mode, then check auto-apply-to-repo
     independently.

     (a) Base classification:
       composite < config.prevalidation.thresholds.discard
           OR diff_lines > config.guardrails.max_diff_lines
           OR simplicity review failed
         -> status=discarded. Write row. Keep artifacts for audit. Continue.

       discard <= composite < config.prevalidation.thresholds.push
         -> status=pre_validated. Keep the variant folder for later
            recombination. Write row. Continue.

     (b) composite >= config.prevalidation.thresholds.push AND simplicity
         review passed AND config.adapters.abtest.id is not null:

         CASE config.workflow.review_mode:

         "off":
           -> status=pre_validated (plan-only). Write row. Continue.

         "manual":
           -> Invoke skills/queue-review.md in ## append mode. The skill
              writes an entry to variants/PENDING.md with
              status: awaiting_review, appends an awaiting_review row to
              results.tsv, and logs event=variant_queued_review. Do NOT
              call push_variant — the drain step (step 0 of the next
              iteration, or an interactive drain prompt) is the only path
              to actually push the variant.

         "auto":
           Compute fast_track_eligible:
             fast_track_eligible =
                  signals.heuristic.raw.blocker_removed != null
               AND signals.heuristic.raw.blocker_removed >= 0.5
               AND diff_lines <= 5
               AND composite >= config.prevalidation.thresholds.push
               AND simplicity_review_passed

           Rationale: a tiny patch (<= 5 lines) that mechanically unbreaks a
           structural blocker on a primary or secondary affordance is a
           high-confidence, low-risk fix — the kind a human would approve in
           seconds. The fast-track lets it skip the standard
           auto_push_threshold (default 0.60) so the framework can
           auto-apply the class of fixes it should be best at: structural
           bug fixes grounded in unambiguous data (e.g., 47% rage-click
           rate on a disabled submit button). Cosmetic copy variants never
           qualify because their blocker_removed is null or 0.

           IF composite >= config.workflow.auto_push_threshold OR fast_track_eligible:
             -> Call abtest.push_variant with
                  allocation_pct = config.workflow.auto_allocation_pct
                (default 50). The test goes LIVE immediately — no 0%
                staging, no human ramp. On success, write
                variants/<slug>/experiment.json, set status=pushed with
                the returned experiment_id, and log
                event=variant_pushed_live. If fast_track_eligible AND
                composite < auto_push_threshold, include
                "fast_track=true; reason=blocker_removed+tiny_diff" in the
                run.log notes so the human can audit which variants took
                the side door. On failure, warn and fall through to the
                queue branch below.
           ELSE (composite < auto_push_threshold AND not fast_track_eligible):
             -> Invoke skills/queue-review.md in ## append mode (same as
                manual). status=awaiting_review.

     (c) composite >= config.prevalidation.thresholds.push
         AND config.adapters.abtest.id IS null
         -> status=pre_validated (abtest is plan-only). Write row. Continue.

     (d) Auto-apply to the parent working tree — orthogonal to the above:
         IF config.workflow.auto_apply_to_repo == true
            AND simplicity review passed
            AND current status is NOT discarded
            AND (composite >= config.workflow.auto_apply_threshold (default 0.70)
                 OR fast_track_eligible)
         -> Apply the patch to the parent project's working tree:

            (Note: fast_track_eligible is computed in branch (b) above when
            review_mode is "auto"; if review_mode is "manual" or "off",
            recompute it here using the same criteria. The fast-track lets a
            tiny mechanical bug-fix patch — e.g., the broken submit button —
            commit straight to the working tree without clearing the 0.70
            bar. The criteria are deliberately narrow: blocker_removed
            heuristic >= 0.5, diff_lines <= 5, composite >= push_threshold,
            simplicity ok.)

              cd <config.project.root>
              git apply --check autocro/variants/<slug>/patch.diff
              git apply autocro/variants/<slug>/patch.diff
              git add -A
              git commit -m "chore(cro): auto-apply <slug>

Composite: <composite>
Hypothesis: <one-line summary from hypothesis.md>
Run tag: <tag>"
            On success: append a status=auto_applied row. Log
              event=variant_auto_applied. If fast_track_eligible AND
              composite < auto_apply_threshold, include
              "fast_track=true; reason=blocker_removed+tiny_diff" in the
              run.log notes so the auto-apply audit trail makes the
              side-door path explicit.
            On git apply failure: do NOT commit. Keep the existing status
              (pre_validated, pushed, or awaiting_review). Log notes:
              "auto-apply failed: <error>".
            Note: auto-apply and A/B push are fully independent — a variant
              can simultaneously be awaiting_review (in manual mode), pushed
              live (in auto mode), AND auto-applied to the working tree,
              depending on the thresholds the human set.

  8. Every config.outer_loop.check_every iterations (default 8), run the
     outer loop poll (skills/read-experiment.md). Update any measuring/pushed
     rows that have reached significance. Never edit old rows; always append
     a new row for each status change.

  9. Invoke skills/rank.md. It re-reads results.tsv and rewrites
     variants/RANKED.md with the current top candidates, using measured_lift
     where available and composite elsewhere.

 10. Check budget:
       variants_proposed >= config.budget.max_variants_per_run
         OR wall_minutes >= config.budget.max_wall_minutes
         OR (config.budget.stop_on_first_push == true
             AND any variant in this session has status=pushed)
         -> print a summary to run.log and stop gracefully.
     Otherwise: continue.

     The `stop_on_first_push` clause counts ONLY successful push_variant
     responses (status=pushed in results.tsv with a non-empty experiment_id).
     awaiting_review variants (queued for human approval) and auto_applied
     variants (committed to the autocro branch but not pushed live) do NOT
     trigger this stop — those are not yet generating live experiment
     traffic. The intent is "once we've created one real PostHog experiment
     this session, hand back to the human to ramp it before generating more
     candidates that could compete for the same conversion population."
```

## NEVER STOP

Once the human has confirmed setup, do NOT pause to ask "should I keep going?" or "is this a good stopping point?". The human might be asleep or away from the computer and expects you to run indefinitely until manually interrupted or until a budget limit is hit. You are autonomous.

If you run out of ideas:

- Re-read the adapter playbooks for capabilities you haven't used yet.
- Re-read the last 50 results rows and look for near-misses to recombine.
- Re-read `harness/judge-rubric.md` and try variants that directly target its checklist items.
- Explore a page you've never touched.
- Try the opposite of a pre_validated variant (e.g. if adding urgency copy worked, try removing urgency copy on a different page to test whether the pattern generalizes).

If you hit a real blocker (every adapter is down, the parent project has uncommitted changes that make patch generation impossible, etc.), write a clear summary to `run.log`, set `status=crash` on any in-flight variants, and stop. Do not flail.

## First run

On your very first run in a fresh setup, your first variant should be a **no-op baseline snapshot**. Write a row to `results.tsv` with `variant_slug=v0000-baseline`, `diff_lines=0`, `status=proposed`, empty scores, and `description=baseline snapshot`. This anchors the ranking system and lets you compute deltas against a known zero. Then begin the real loop at step 1.
