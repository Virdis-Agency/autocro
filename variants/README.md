# variants/

Agent output. Each variant is a folder under `variants/v####-kebab-slug/`. This whole directory is gitignored — the agent regenerates it every run.

Two top-level files also live here:
- `RANKED.md` — rewritten by `skills/rank.md` with the current top candidates.
- `PENDING.md` — the review queue for `workflow.review_mode: "manual"`, written by `skills/queue-review.md`. Edit the `status:` line on a block to `approved`, `rejected`, or `deferred` to control what the next drain does.

## Folder format

```
variants/v0042-pricing-cta-specificity/
├── hypothesis.md          <- required: why, data citations, predicted lift
├── patch.diff             <- required: git-applyable against parent HEAD
├── pre-validation.json    <- written by skills/pre-validate.md
├── experiment.json        <- optional: written after abtest push succeeds
├── notes.md               <- optional: running notes + rejected sub-variants
└── sources/               <- optional: raw adapter responses that informed the hypothesis
```

## Slug format

`v{NNNN}-{kebab-case}`

- `NNNN` is a zero-padded 4-digit sequential number. `v0001` is the first variant. `v0000` is reserved for the baseline snapshot.
- `kebab-case` is 2–5 lowercase words separated by hyphens, describing the change.
- Good: `v0042-pricing-cta-specificity`, `v0017-hero-fluff-removal`, `v0003-signup-fewer-fields`
- Bad: `v42-change`, `variant_42`, `v0042-REPLACE-LEARN-MORE-BUTTON`

## hypothesis.md

A short markdown file the human reads when triaging results. Template at `skills/generate-variant.md`. Must include: research direction, iteration number, one-sentence summary, proposed change, data citations with adapter ID + capability, predicted lift band, reasoning, simplicity rationale.

## patch.diff

Unified diff against the parent project's HEAD at the moment the variant was generated. Format:

```
diff --git a/<path> b/<path>
--- a/<path>
+++ b/<path>
@@ -<old> +<new> @@
  context
- removed
+ added
  context
```

Must be applyable via `git apply --check` from the parent project root. The inner loop verifies this in step 6 before scoring.

## pre-validation.json

Written by `skills/pre-validate.md` after scoring. Contains per-signal raw arrays (not just averages) so the analysis notebook can display error bars. Shape documented in `skills/pre-validate.md`.

## experiment.json

Written by `skills/queue-review.md` (drain step, manual mode) or by the inner-loop step 7 cascade (auto mode) when the variant is successfully pushed to an abtest adapter. Contains:

```json
{
  "experiment_id": "<adapter-defined>",
  "adapter": "<adapter id>",
  "allocation": 0.5,
  "allocation_pct": 50,
  "started_at": "<ISO-8601>",
  "status": "running | plan_only",
  "description": "<short>"
}
```

In `review_mode: "manual"` (the default), `allocation` is always `0.0` and the human ramps manually via the abtest tool. In `review_mode: "auto"`, `allocation` reflects `config.workflow.auto_allocation_pct / 100` — the test goes live immediately at that split.

## notes.md

Free-form notes the agent writes during generation. Typically:

- The iteration number and research direction.
- Sub-variants considered and rejected (one line each).
- Any deviation from the usual flow (e.g. "skipped heatmap adapter because it was unhealthy this round").
- The `simplicity-review` decision line.

## sources/

Raw adapter responses copied here when the agent wants them in version control alongside the hypothesis. Not always populated — only when the data is small enough to store and the agent wants it for later reference during recombine-direction iterations.

## RANKED.md

Written by `skills/rank.md` after each iteration. A ranked markdown table of the current top candidates across all variants, scored by `measured_lift` where available and `composite` otherwise. Also gitignored. This is what the human looks at first when waking up after an overnight run.

## Applying a variant to your parent project

The framework never applies patches to your working tree automatically. To apply a variant manually:

```bash
cd <parent project root>
git apply --check autocro/variants/v0042-pricing-cta-specificity/patch.diff
git apply       autocro/variants/v0042-pricing-cta-specificity/patch.diff
```

Inspect the change, commit it yourself, and ship.
