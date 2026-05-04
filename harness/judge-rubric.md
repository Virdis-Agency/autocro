# Judge rubric

Used by `skills/pre-validate.md` to score a variant's LLM-judge signal. Each panel pass (default 5) reads this full rubric, the variant's hypothesis, the variant's `patch.diff`, the relevant "before" content from the parent project, and a seed. Each pass returns a single float in `[-1, +1]`.

The rubric emphasizes **concrete, checkable properties** and **explicitly penalizes AI-fluff copy** so the composite score doesn't drift into "an LLM that loves what LLMs write" territory.

## How to run a single panel pass

Given:
- `hypothesis.md`
- `patch.diff`
- The "before" files from the parent project (so you can compare)
- A seed (`config.prevalidation.llm_judge.seed`, default `42`)

Return a single JSON object:

```json
{
  "items": {
    "cta_clarity":       {"score": 1, "reason": "..."},
    "cta_specificity":   {"score": 1, "reason": "..."},
    "value_prop_concrete":{"score": 0, "reason": "..."},
    "friction_reduction":{"score": 1, "reason": "..."},
    "social_proof_real": {"score": 0, "reason": "..."},
    "copy_concreteness": {"score": 1, "reason": "..."},
    "copy_antifluff":    {"score": 0, "reason": "..."},
    "visual_hierarchy":  {"score": 0, "reason": "..."},
    "mobile_first":      {"score": 0, "reason": "..."},
    "accessibility":     {"score": 0, "reason": "..."},
    "blocker_removed":   {"score": 0, "reason": "..."}
  },
  "composite": 0.385,
  "seed": 42,
  "notes": "..."
}
```

Each `items.*.score` is one of `-1`, `0`, `+1`. The `composite` is the **weighted** mean of all items (see "Composite calculation" below), mapped to `[-1, +1]`. Most items carry weight 1; `friction_reduction` and `blocker_removed` carry weight 2 because they directly measure impact on the goal-completion path.

## The items

Score each item independently. For each, output `-1` (worse than baseline), `0` (neutral or not applicable), or `+1` (clearly improved). Give a one-sentence `reason` citing a specific line or element from the diff.

### 1. CTA clarity

Does the patched primary CTA clearly describe what happens when the user clicks it, in 5 words or fewer?

- `+1`: "Start free trial", "Create my account", "Download the 2026 report", "Get instant demo"
- `0`: "Continue", "Next step", "Sign up", existing good CTAs unchanged
- `-1`: "Learn more", "Read more", "Click here", "Get started" (without specificity), new vague CTAs introduced

### 2. CTA specificity

Does the CTA name the specific outcome (free trial, account, demo, report name, etc.) rather than a generic action?

- `+1`: names the thing ("Start 14-day trial", "Download state of AI 2026")
- `0`: generic but active ("Start now", "Get the guide")
- `-1`: abstract or passive ("Learn", "Explore", "Discover")

### 3. Value prop concreteness

Does the patch make the value proposition more specific, quantified, or outcome-oriented?

- `+1`: replaces a vague benefit with a number, timeframe, or named outcome ("Ship 3× faster" → "Deploy in under 5 minutes")
- `0`: unchanged or still abstract
- `-1`: makes it vaguer, more adjective-heavy ("amazing", "revolutionary", "cutting-edge")

### 4. Friction reduction

Does the patch reduce the number of steps, clicks, or required form fields to reach the goal?

- `+1`: removes a required field, removes a step, defaults a sensible value, auto-fills from context
- `0`: no change to friction
- `-1`: adds a step, adds a required field, adds a confirmation dialog, adds a captcha

### 5. Social proof realism

Does the patch add or strengthen concrete, quantified, third-party social proof — not "trusted by leading companies" but actual numbers, logos, or verified testimonials?

- `+1`: adds real numbers ("4,200 companies", "★ 4.9 from 3,100 reviews"), named customer logos, or attributed testimonials
- `0`: unchanged, or adds generic trust language without numbers
- `-1`: adds unquantified/vague claims ("loved by customers", "trusted worldwide") OR removes existing concrete proof

### 6. Copy concreteness

Does the patched copy use specific nouns, verbs, and numbers instead of abstractions?

- `+1`: uses concrete nouns ("the invoice", "your team", "customers in 40 countries") and active verbs
- `0`: mixed
- `-1`: uses abstract nouns ("solutions", "experiences", "capabilities"), passive voice, or nominalizations ("enablement", "facilitation", "optimization")

### 7. Copy anti-fluff

Is the patch free of AI-generated-sounding marketing fluff?

- `+1`: Zero fluff. Every sentence could appear in a human-written technical blog post.
- `0`: One or two soft phrases, but not dominant.
- `-1`: Contains any of these common fluff phrases (deduct one point each, floor at `-1`):
  - "unlock your potential"
  - "take X to the next level"
  - "game-changing", "revolutionary", "cutting-edge"
  - "seamlessly integrate"
  - "empower your team"
  - "supercharge"
  - "leverage" (as a verb meaning "use")
  - "in today's fast-paced world"
  - "at the end of the day"
  - "world-class", "best-in-class"
  - "transform your X"
  - "elevate your X"
  - "drive meaningful outcomes"
  - "in this digital age"

**This item is the most important.** AI-written copy loses trust immediately. A +1 on every other item cannot save a patch that scores -1 here.

### 8. Visual hierarchy

If the patch changes layout, typography, or color, does it improve how quickly the eye finds the primary action?

- `+1`: primary CTA becomes more prominent (larger, brighter, better contrast, more whitespace around it) OR de-cluttering reduces competing elements
- `0`: no layout change, or changes are lateral
- `-1`: primary CTA becomes less prominent, or visual noise increases

### 9. Mobile-first

Is the change mobile-friendly? Would it render acceptably on a 375px-wide screen?

- `+1`: explicit mobile improvement (responsive classes, smaller font on small, stacked layout)
- `0`: no impact on mobile
- `-1`: uses fixed widths, desktop-only assumptions (hover states as the only affordance), or breaks responsive layout

### 10. Accessibility

Does the change maintain or improve accessibility (alt text, semantic HTML, ARIA roles, focus order, color contrast, keyboard navigation)?

- `+1`: adds alt text, semantic elements, aria labels, or improves contrast / focus
- `0`: no accessibility impact
- `-1`: uses divs where semantic elements belong, removes alt text, introduces low-contrast pairings, or breaks keyboard navigation

### 11. Blocker removed

Does the patch remove a structural impediment that prevents users from completing the goal event? Examples: a `disabled` attribute on a submit button, a `pointer-events: none` style on the primary CTA, an `href="#"` placeholder on what should be a working link, an empty form `action`, a `tabindex="-1"` trapping keyboard users away from a needed control, a CSS class like `cta-disabled` that the LLM can recognize as an off-state.

This item is distinct from `friction_reduction` (#4): friction is *"one more step than ideal"*; a blocker is *"no path to the goal at all."* A patch can score +1 on both independently — e.g., removing `disabled` AND removing two unnecessary form fields.

- `+1`: removes a blocker on the **primary** CTA / submit / goal-event element
- `0`: no blocker addressed (most patches)
- `-1`: introduces a blocker on the primary CTA / submit / goal-event element

This item carries **weight 2** in the composite (see below). It pairs with the deterministic `blocker_removed` sub-score in `skills/pre-validate.md` — the heuristic catches literal attribute/CSS patterns; this item catches semantic equivalents the heuristic can't pattern-match.

## Composite calculation

Items are not equally weighted. Items that capture impact on the goal-completion path (`friction_reduction`, `blocker_removed`) carry double weight; the remaining 9 items carry weight 1.

```
weights = {
    "cta_clarity":          1,
    "cta_specificity":      1,
    "value_prop_concrete":  1,
    "friction_reduction":   2,
    "social_proof_real":    1,
    "copy_concreteness":    1,
    "copy_antifluff":       1,
    "visual_hierarchy":     1,
    "mobile_first":         1,
    "accessibility":        1,
    "blocker_removed":      2,
}
total_weight = 13
composite = sum(items[k].score * weights[k] for k in items) / total_weight
```

With 11 items and a denominator of 13, composite is in `[-1, +1]`. Granularity is no longer a clean 0.1 — the smallest non-zero step is `1/13 ≈ 0.077`.

**Clamp rule**: if `copy_antifluff` is `-1`, the overall composite is clamped to `min(composite, 0.0)` — a fluffy patch cannot score positive overall no matter how good the rest is. The clamp runs AFTER the weighted average, so it stays effective regardless of how the friction or blocker items score.

## Seed usage

The seed is included in this prompt so repeated passes are quasi-deterministic. Use it to stabilize any tie-breaking between equal-score items: if two items are borderline, bias the decision by the parity of the seed. This is hand-wavy by design — the goal is to reduce variance across the 5-pass panel, not achieve perfect determinism.

## Anti-patterns to call out in `notes`

If the patch exhibits any of these, mention them explicitly in the `notes` field so the human can see why a panel pass scored low:

- "Commented-out old code left in."
- "Uses `!important` instead of fixing CSS specificity."
- "Introduces a new component for a one-line change."
- "Adds a hook / effect / observer to do what inline JSX could do."
- "Misspelled word in visible copy."
- "Broken link or placeholder href (`#`, `javascript:void`)."
- "Debug statement left in (`console.log`, `alert`, `TODO`)."

These are hints to `skills/simplicity-review.md` which may auto-discard.
