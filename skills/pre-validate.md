# Skill: pre-validate

Score a generated variant across the enabled signals and write a single composite to `variants/<slug>/pre-validation.json`.

## Inputs

- A variant folder at `variants/<slug>/` containing `hypothesis.md` and `patch.diff`.
- `config.prevalidation` with enabled signals, weights, and thresholds.
- `harness/judge-rubric.md`.
- The parent project's HEAD (for context when scoring the patch).

## Output

Write `variants/<slug>/pre-validation.json` in this shape:

```json
{
  "slug": "v0042-pricing-cta-specificity",
  "timestamp": "2026-04-10T02:14:05Z",
  "diff_lines": 14,
  "signals": {
    "heuristic": {
      "enabled": true,
      "score": 0.31,
      "raw": {
        "cta_verb_quality": 0.5,
        "readability_grade": -0.1,
        "social_proof_presence": 0.2,
        "contrast_ratio": 0.0,
        "form_friction": 0.4,
        "mobile_viewport_meta": 0.0,
        "blocker_removed": null
      },
      "notes": "CTA verb changed from 'Learn more' to 'Start free trial' — +0.5"
    },
    "llm_judge": {
      "enabled": true,
      "panel_size": 5,
      "seed": 42,
      "raw_panel": [0.40, 0.35, 0.42, 0.38, 0.45],
      "score": 0.40,
      "is_stochastic": false
    },
    "lighthouse": {
      "enabled": false
    },
    "persona": {
      "enabled": false
    }
  },
  "weights_renormalized": {
    "heuristic": 0.273,
    "llm_judge": 0.727
  },
  "composite": 0.375
}
```

Return the composite score to the inner loop as a single float.

## Heuristic signal (zero-dep, deterministic)

Run these checks against the patch and the patched file contents (apply the patch mentally or via a scratch read — do NOT mutate the user's working tree). Each sub-score is in `[-1, +1]`. Average them and map back to `[-1, +1]` for the heuristic signal score.

### 1. CTA verb quality (`cta_verb_quality`)

Look for `<a>`, `<button>`, or click-handler text changed in the diff. Score:

- **+1.0**: task-specific action verb naming the outcome ("Start free trial", "Create account", "Get instant demo", "Download report")
- **+0.5**: strong action verb without specificity ("Get started", "Try it free")
- **+0.0**: neutral ("Continue", "Next", "Sign up")
- **−0.5**: vague ("Learn more", "Click here", "Read more")
- **−1.0**: made worse or new vague CTA introduced

If the diff does not touch a CTA, set `cta_verb_quality` to `null` and exclude from the average.

### 2. Readability grade (`readability_grade`)

Extract copy changes from the diff. Compute Flesch-Kincaid grade on the NEW copy and the OLD copy. Score:

- **+1.0**: grade dropped by ≥ 3 (copy got easier) AND new grade ≤ 9
- **+0.5**: grade dropped by ≥ 1
- **+0.0**: ±1 grade change
- **−0.5**: grade rose by ≥ 1
- **−1.0**: grade rose by ≥ 3 OR new grade ≥ 14

If no copy changes, set to `null`.

### 3. Social proof presence (`social_proof_presence`)

Does the diff add/remove quantified social proof ("4,200 companies", "★ 4.9 from 3,100 reviews", named customer logos)?

- **+1.0**: adds new quantified social proof
- **+0.5**: strengthens existing (e.g., adds a number to an existing mention)
- **+0.0**: no change
- **−0.5**: removes some
- **−1.0**: removes all

### 4. Contrast ratio (`contrast_ratio`)

If the diff touches CSS colors or text-on-background pairs, compute WCAG contrast ratio (or use the `accesslint:contrast-checker` skill if available). Score:

- **+1.0**: raises contrast from failing (< 4.5:1 for body text, < 3:1 for large) to passing
- **+0.5**: raises passing contrast further
- **+0.0**: no change
- **−0.5**: lowers passing contrast while staying above threshold
- **−1.0**: drops below WCAG AA threshold

If no color changes, set to `null`.

### 5. Form friction (`form_friction`)

Count form fields before and after the diff. Score:

- **+1.0**: removes ≥ 2 required fields without losing meaningful data
- **+0.5**: removes 1 required field, or makes required → optional
- **+0.0**: no change
- **−0.5**: adds 1 field
- **−1.0**: adds ≥ 2 fields or makes optional → required

If no form changes, set to `null`.

### 6. Mobile viewport meta (`mobile_viewport_meta`)

Does the patched HTML have `<meta name="viewport" content="width=device-width, initial-scale=1">` on target pages? +1 if it was missing and is now present; 0 if unchanged (present or irrelevant); −1 if removed.

### 7. Blocker removed (`blocker_removed`)

Detect attributes, inline styles, hrefs, or form actions in the diff that prevent users from completing the goal action. This is distinct from `form_friction` (#5) which counts fields — a blocker is "no path to the goal at all," not "one extra step."

Trigger patterns (any one is enough; check both removals AND additions):

- **HTML attributes** on interactive elements: `disabled`, `aria-disabled="true"`, `readonly` (on an input expected to take input), `tabindex="-1"` (on a focusable control)
- **Inline / style-attribute CSS** on a primary CTA selector: `pointer-events: none`, `display: none`, `visibility: hidden`, `opacity: 0`
- **Broken hrefs**: `href="#"`, `href="javascript:void(0)"`, `href="javascript:;"`, empty `href=""`
- **Form submission**: form `action` attribute is empty (`action=""`) or missing entirely on a form whose submit is the goal event

Identify which element is the **primary** affordance: the one tied to `config.goal.event`. On forms, that's the submit button or the form `action`. On link-driven funnels, that's the CTA matching `goal.target_paths`.

Score:

- **+1.0**: removes one of the above from the **primary** CTA / submit / goal-event element
- **+0.5**: removes one from a **secondary** affordance (nav link, secondary CTA, non-goal form)
- **+0.0**: no change to blockers
- **−0.5**: introduces a soft blocker on a secondary element
- **−1.0**: introduces a blocker on the primary CTA / submit / goal-event element

If the diff doesn't touch any of the trigger patterns above, set to `null` and exclude from the heuristic mean — same convention as the other sub-scores.

This sub-score is the deterministic counterpart to rubric item #11 in `harness/judge-rubric.md`. The two run independently and can disagree (e.g., the LLM may catch a blocker-equivalent class change like `class="cta-disabled"` that this pattern list misses, or vice versa). Both should agree on obvious cases (a literal `disabled` attribute on a submit button).

### Aggregation

```
enabled = [s for s in sub_scores if s is not null]
heuristic_score = mean(enabled) if len(enabled) > 0 else 0.0
```

## LLM judge signal (zero-dep, panel-averaged)

Invoke the rubric in `harness/judge-rubric.md` once per panel pass (default 5 passes). Each pass gets a fresh prompt that includes:

1. The full contents of `harness/judge-rubric.md`.
2. The hypothesis from `hypothesis.md`.
3. The diff from `patch.diff`.
4. The relevant "before" content from the parent project.
5. The seed from `config.prevalidation.llm_judge.seed` (used as a salt in the rubric instructions to reduce variance).

Each pass must return a single float in `[-1, +1]`. Store the raw panel array in `signals.llm_judge.raw_panel`. The signal score is the panel mean.

If any pass returns something outside `[-1, +1]` or non-numeric, clamp to the range and add a note to `signals.llm_judge.notes`.

Set `is_stochastic: false` — the rubric + seed combination is designed to be quasi-deterministic across runs.

## Lighthouse signal (Phase 2, opt-in)

If `config.prevalidation.lighthouse.enabled` is true:

1. `skills/setup-check.md` step 7g is expected to have already confirmed that `harness/lighthouse.sh` and `harness/apply-patch.sh` exist; if this skill is invoked with lighthouse enabled and either helper is missing, stop with an error pointing back at setup-check. Also confirm Node is available.
2. Create a scratch worktree at `~/.cache/autocro/worktrees/<slug>/`.
3. Apply `patch.diff` there via `harness/apply-patch.sh`.
4. Serve or navigate to `config.project.baseline_url` in that worktree.
5. Run `harness/lighthouse.sh <url>` and parse the JSON for the configured categories.
6. Compute delta vs a cached baseline score (cache at `~/.cache/autocro/baseline-lighthouse.json`, refresh weekly).
7. Map each category delta to `[-1, +1]` (a 10-point Lighthouse delta ≈ 0.5 signal score).
8. Average across categories for the signal score.
9. Tear down the worktree.

If Lighthouse fails, set `signals.lighthouse.enabled: false` for this variant and add a note.

## Persona signal (Phase 3, opt-in)

If `config.prevalidation.persona.enabled` is true, follow `harness/persona-sim.md`. Set `is_stochastic: true`.

## Composite calculation

```
enabled_signals = [s for s in signals if signals[s].enabled]
weight_sum = sum(config.prevalidation.weights[s] for s in enabled_signals)
for s in enabled_signals:
    renormalized[s] = config.prevalidation.weights[s] / weight_sum

composite = sum(signals[s].score * renormalized[s] for s in enabled_signals)
```

Clamp composite to `[-1, +1]` as a final safety.

## Write the file

Write `variants/<slug>/pre-validation.json` with the full shape shown at the top. Return the composite float to the inner loop.

## Do not

- Do not mutate `patch.diff` from this skill.
- Do not apply the patch to the parent's working tree.
- Do not update `results.tsv` from this skill — the inner loop writes the row.
- Do not ask the human to pick a score or break a tie. Compute deterministically.
