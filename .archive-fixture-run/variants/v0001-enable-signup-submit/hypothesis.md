# v0001-enable-signup-submit

**Research direction**: explore
**Iteration**: 1

## Summary

Remove the literal `disabled` attribute on the signup-form submit button — it blocks the goal `sign_up` event for every visitor who reaches it, producing a 47% rage-click rate.

## Proposed change

`fixtures/demo-target/index.html` line 117: drop the ` disabled` attribute from the `<button type="submit" class="btn btn-submit" disabled>Submit</button>` element. One-attribute removal; no copy, layout, validation, or form-field change.

## Data citations

- `fixture:rage_clicks`: `/signup` `button[type='submit']` shows 582 rage clicks at a 47% rage-click rate; sample note: "users clicking the disabled submit button repeatedly; most sessions then abandon".
- `fixture:funnel`: `submit` step entered=420, advanced=96 — a 77% drop at the very last step, while every prior step retains a meaningful share.
- `fixture:page_attention`: `/signup` submit-button hotspot intensity 0.96 (highest on the page) — visitors are actively trying to use it.
- `fixture:click_map`: `/signup` `button[type='submit']` has 1,240 total clicks (more than the email field's 980), confirming users reach and engage the control.

## Predicted lift band

4% to 12% absolute conversion lift on `/signup` (current functional submit rate is effectively 0%; band is conservative because some abandoners may not return even after the fix).

## Reasoning

The HTML `disabled` attribute on a button bound to the goal-event submit is the canonical primary-affordance blocker — `harness/judge-rubric.md` item #11 and `pre-validate.md` heuristic `blocker_removed`. Heatmap data shows users complete the form, click submit, get no response, rage-click, and abandon; the funnel confirms the drop is concentrated entirely at the submit step. The fix is mechanical: remove one attribute, restore the goal path. A larger redesign isn't justified — every prior funnel step works.

## Simplicity rationale

Smallest possible change that addresses the cited blocker: removing 16 characters from a single line. No new abstractions, no framework gymnastics, no copy debate. If this fix doesn't move the needle, the fixture data is wrong; nothing else explains the pattern.
