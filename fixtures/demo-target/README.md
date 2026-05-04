# fixtures/demo-target

A deliberately weak marketing site for Acme Cloud. Used as the end-to-end smoke test target for autocro — drop the framework into this folder, run one inner-loop iteration in fixture mode, and verify that the agent produces a sensible ranked list of variants.

## Deliberate CRO weaknesses

This site has every common conversion problem so the agent always has something to work with:

**Copy (anti-fluff rubric should light up):**
- Hero headline: "Unlock your team's potential with cutting-edge cloud solutions" — three fluff phrases in one sentence.
- Hero sub: "empower... seamlessly leverage... in today's fast-paced world... take your infrastructure to the next level... revolutionary" — saturated.
- Features section: "Amazing features that transform your workflow" — passive, adjective-heavy.
- Every feature card starts with a one-word abstract adjective and ends in fluff.

**CTAs (CTA clarity / specificity rubric should light up):**
- EVERY CTA is "Learn more". Hero, every pricing card, enterprise contact.
- Signup button is literally labeled "Submit" AND `disabled` by default.
- No outcome-specific language anywhere.

**Social proof (social_proof_real rubric):**
- "Trusted by leading companies worldwide" with no numbers, no logos, no names, no testimonials.

**Form friction (form_friction rubric):**
- 11 required fields on signup, including phone number, country, job title, company size, password + confirm-password.
- No progressive disclosure.
- Submit button `disabled` with no indication of what enables it.

**Pricing (simplification opportunity):**
- Four tiers when three would suffice — Starter, Team, Business, Enterprise. Team is the "featured" but the distinction between Business and Team is thin.

**Visual hierarchy / contrast (contrast rubric):**
- Background `#f4f4f4`, body text `#555`, headings `#777-#888`, muted links `#999-#aaa`, `btn-primary` background `#c0c0c0` on white text. Half the contrast pairs fail WCAG AA for body text. Deliberate.
- All buttons look alike visually — the primary CTA does not stand out.

**Mobile-first:**
- No viewport meta tag.
- `grid-template-columns: repeat(4, 1fr)` on pricing with no responsive breakpoint.
- Fixed max-widths everywhere.

**Accessibility:**
- `<select>` has no aria-describedby for the empty option.
- `input` elements all inside `<label>` but without explicit `for/id` association.
- `disabled` button with no explanation.

## Using this target

This demo lives inside the framework. Open Claude Code at the **parent of `autocro/`** (mirroring the drop-in layout from the top-level README) — `autocro/` is the framework, and `autocro/fixtures/demo-target/` is the parent project being optimized. Every skill hardcodes `autocro/...` paths, so opening Claude Code anywhere deeper inside the tree will break the first call to setup-check.

From that cwd:

```
cp autocro/config.example.yaml autocro/config.yaml
# edit autocro/config.yaml:
#   project.root: "fixtures/demo-target"   # relative to autocro/
#   mode: fixture
#   adapters.{analytics,heatmap,abtest}.id: fixture
```

Then prompt the agent:

> Read `autocro/program.md` and run one inner-loop iteration.

Inspect `autocro/variants/v0001-*/hypothesis.md`, `autocro/variants/v0001-*/patch.diff`, and `autocro/results.tsv`. The patch should apply cleanly to `autocro/fixtures/demo-target/` via `git apply --check`.

Expected first-iteration behavior: the agent picks up one of the obvious weaknesses (CTA text, form bloat, pricing tier count, or fluff copy), proposes a small patch, scores it with the judge rubric and heuristics, writes a row to `results.tsv`, and writes the variant folder.

## Intentional fixture invariant

The weaknesses in this site match the canned weaknesses described in `fixtures/analytics-sample.json` and `fixtures/heatmap-sample.json`. That way, hypothesis citations from the fixture analytics adapter point at real problems you can see in the HTML.
