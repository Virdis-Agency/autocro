# Auto Conversion Rate Optimization (CRO)

Autonomous conversion rate optimization research as a drop-in folder for any website project.

> **AutoCRO · Virdis fork** — production fork of the autocro framework
> (a Karpathy-style autoresearch loop retargeted at conversion rate
> optimization), maintained by [Virdis](https://virdis.io). We're rolling
> this out across virdis.io and SaaS client sites. The upstream
> documentation is preserved verbatim below.

## Install — drop into your project (60 seconds)

AutoCRO is a **drop-in subfolder**, not a package. You don't `npm install`
it — you clone it as a folder named `autocro/` at the root of any website
project (Next.js, Astro, plain HTML, WordPress, Rails, anything).

**1. Clone into your project root:**

```bash
# from the root of your website project:
gh repo clone Virdis-Agency/autocro
# or, without the gh CLI:
git clone https://github.com/Virdis-Agency/autocro.git
```

You should now have an `autocro/` folder sitting next to your `package.json`,
`Gemfile`, `index.html`, or whatever the root of your site is.

**2. Tell your parent repo to ignore it** (recommended — keeps the autocro
git history separate from your website's):

```bash
echo "autocro/" >> .gitignore
```

**3. Copy the example config:**

```bash
cp autocro/config.example.yaml autocro/config.yaml
```

`config.yaml` is gitignored inside the autocro repo, so any local
credentials and project-specific tweaks stay on your machine.

**4. Open coding agent in your project root and prompt:**

> Read `autocro/program.md` and run **one** inner-loop iteration using fixture
> adapters.

That's it. The first run uses bundled offline fixtures so you don't need any
API keys — it produces a sample variant patch in `autocro/variants/v0001-*/`
and writes a row to `autocro/results.tsv`. From there, follow the
[**Quick start**](#quick-start) section below to wire up your real analytics,
heatmap, and A/B-testing tools.

---

## About this fork

AutoCRO is a drop-in folder that runs an overnight CRO research loop against
any website project. You give it read access to your analytics, heatmaps, and
A/B-testing tools, and in the morning you get a ranked list of small,
reviewable variant patches — each one grounded in real data from your own
tools, pre-validated by an LLM judge panel and heuristic scoring, and
optionally already queued as a 0%-allocation experiment in whichever A/B
testing tool you pointed it at.

This fork ([Virdis-Agency/autocro](https://github.com/Virdis-Agency/autocro))
is what we run in production at Virdis. Over time we'll publish:

- **Production-tested adapter playbooks** for the tools we use most — PostHog
  (analytics + experiments), Microsoft Clarity (heatmaps), GrowthBook, and
  others as we wire them up.
- **Hypothesis seeds and judge-rubric tuning** for SaaS marketing sites,
  pricing pages, and onboarding funnels.
- **Anonymized case studies** from running AutoCRO against real client sites.

If you want AutoCRO running on your own site without standing it up yourself,
it's part of our CRO engagement — see [virdis.io](https://virdis.io).

## Why we forked

CRO at most agencies looks like this: someone stares at heatmaps for an hour,
forms a hypothesis, writes a variant, ships it to GrowthBook at 50/50, waits
two weeks, repeats. It's slow, it's expensive, and the bottleneck is human
attention — not data, not engineering, not creativity.

The autoresearch architecture — a tight `program.md` skill, a
`generate → evaluate → keep/discard → log` loop, and a flat `results.tsv`
memory — is exactly the right shape for that problem. AutoCRO retargets it
from LLM pretraining at a website's `app/` and `components/` directories.
The agent does the staring; we do the judgment.

We forked so we can:

1. **Own the adapters our team relies on** and ship improvements without
   waiting on upstream.
2. **Keep our internal hypothesis libraries and rubric tuning** in one place,
   versioned alongside the framework that consumes them.
3. **Run it against [virdis.io](https://virdis.io) itself** — the agency site
   you're reading about *is* the first parent project this fork operates on.

We follow upstream and contribute fixes back when they're generally useful.

## About Virdis

[Virdis](https://virdis.io) builds fast, conversion-focused websites for
growth-stage SaaS companies. Next.js, PostHog, GrowthBook, Sanity. On time, on
spec, no surprises. If you want a site that ships *and* gets measurably better
every month, [book a call](https://virdis.io/book-a-call).

Follow us on X: [@virdis](https://x.com/virdis).

---

# Auto Conversion Rate Optimization (CRO)

Autonomous conversion rate optimization research as a drop-in folder for any website project.

You drop this folder into the root of your website project, spend ~10 minutes telling the agent what analytics / heatmap / A/B testing tools you use, and then let it run overnight. In the morning you wake up to a ranked list of variant ideas — each one is a small, reviewable code diff against your project, grounded in real data from your own tools, pre-validated by an LLM judge panel + heuristic scoring, and (optionally) already queued as a 0%-allocation experiment in whichever A/B testing tool you pointed it at.

This is a fork of [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) retargeted from LLM pretraining to CRO. The architectural spirit is unchanged: `program.md` is a lightweight skill you iterate on, the agent runs a tight `generate → evaluate → keep/discard → log` loop, `results.tsv` is the memory, and it never stops until you stop it.

## What makes it different

- **Drop-in, tech-stack-agnostic.** Works on Next.js, Astro, plain HTML, WordPress, Rails, Django, SvelteKit — anything. The tool only reads files via a configurable glob allowlist and writes variant patches to its own folder.
- **Reference adapters + authoring skill.** Ships ready-to-use reference adapters for the common tools (GA4, Plausible, PostHog, Microsoft Clarity, GrowthBook). For anything else, `skills/author-adapter.md` walks you through writing a markdown adapter playbook for your tool, interactively.
- **Fail-fast setup.** A mechanical validation layer (`skills/setup-check.md` + `skills/validate-adapter.md` + `harness/validate.py`) checks your `config.yaml`, verifies required env vars are set, and validates every adapter capability against a JSON-schema contract before the inner loop runs. Misconfigurations and adapter shape bugs surface at setup time with a line-addressed, actionable error — never hours later as confusing output.
- **Safe by default.** Patches live in `variants/`, never applied to your working tree. Denied globs protect `.env`, `auth/`, `payment/`, `node_modules/`, `.git/`. The default `review_mode: "manual"` queues every variant in `variants/PENDING.md` and waits for explicit human approval (either by editing the file or via the interactive drain prompt) before anything is pushed to your A/B tool. Opt into `review_mode: "auto"` if you want variants above `auto_push_threshold` to go live automatically at `auto_allocation_pct` traffic (default 50 — an even split with control).
- **Two loops.** A fast **inner loop** (minutes per iteration) generates and pre-validates variants using LLM judges + heuristics. A slow **outer loop** (days) reads real experiment results from your A/B tool once they're statistically significant and promotes winners. The inner loop runs overnight; the outer loop runs whenever you prompt it. Each test's minimum bake time is controlled by `workflow.test_window` (e.g. `{value: 2, unit: "weeks"}`) so you can match your traffic volume, and `on_winner: queue_followup` automatically feeds winning hypotheses back into the inner loop as seeds for follow-up tests.
- **No third-party dependencies.** Everything is markdown skills + adapters the agent executes. The validation helpers under `harness/` are stdlib-only Python. Optional Lighthouse and Playwright helpers are Node-only and opt-in.

## Prerequisites

This framework is **not a standalone runtime**. It runs inside an agent harness that can execute markdown skills with real tool calls. Required:

- **Any compatible harness** that can run `curl`, `git`, `python3`, `jq`, file I/O, and optional MCP tools from inside a markdown playbook). This is what executes `program.md`, the skills, and the adapter playbooks.
- **`python3` ≥ 3.10** — used by the stdlib-only validators under `harness/`. No third-party packages required. Ships with every modern macOS/Linux. Install via `brew install python@3.11` or your distro's package manager if missing.
- **`git`**, **`curl`**, **`jq`** on `PATH`.
- A **parent website project** to drop this folder into.

Optional (opt-in, Phase 2/3):

- **Node.js + Playwright** — required only if you enable `prevalidation.persona` in `config.yaml`.
- **Lighthouse CLI** — required only if you enable `prevalidation.lighthouse`.

You do NOT need to `pip install` anything. The `pyproject.toml` in this repo declares zero dependencies on purpose — the `harness/*.py` files are stdlib-only.

## How it works

```
                   +---------------------+
                   |  Your parent repo   |
                   |  (Next.js / WP /    |
                   |   anything)         |
                   +----------+----------+
                              |
                 drop in as a subfolder:
                              |
                              v
                   +---------------------+
                   |  autocro/  |
                   |                     |
                   |  program.md  ◄──── you iterate on this
                   |  skills/           (author-adapter, hypothesize, ...)
                   |  adapters/         (TEMPLATE + null + fixture shipped)
                   |  harness/          (judge rubric, optional Lighthouse)
                   |  fixtures/         (offline smoke test)
                   |  variants/  ◄──── agent writes here (gitignored)
                   |  results.tsv ◄──── 14-col memory (gitignored)
                   +---------------------+
```

The agent's inner loop, at a glance:

1. Read analytics + heatmap data via your adapters.
2. Form 1–3 hypotheses. Pick the simplest.
3. Generate a patch diff against your parent project.
4. Pre-validate: LLM judge panel + heuristic score → composite.
5. Keep, discard, or push to A/B test adapter based on composite and diff size.
6. Log to `results.tsv`. Continue forever.

## Quick start

### Option A — try it offline first (no accounts needed)

```bash
# From the root of your website project, with this framework at ./autocro:
cp autocro/config.example.yaml autocro/config.yaml
# edit config.yaml:
#   project.root: ".."   # parent project root, relative to autocro/
#   project.baseline_url: "http://localhost:3000"   # whatever you serve
#   mode: fixture
#   adapters.analytics.id: fixture
#   adapters.heatmap.id:   fixture
#   adapters.abtest.id:    fixture
```

If you cloned this repo by itself (no parent project yet), run the commands
from the directory **above** the clone — that way `autocro/` sits as a
subfolder, matching the drop-in layout above. To smoke-test against the
bundled demo site without wiring up a real parent project, set
`project.root: "fixtures/demo-target"` (relative to `autocro/`) in
`autocro/config.yaml`. Do NOT open your agent harness from inside the clone root;
every skill hardcodes `autocro/...` paths and they will not resolve.

Then open your agent harness in your project root and prompt:

> Read `autocro/program.md` and run **one** inner-loop iteration using fixture adapters.

Inspect `autocro/results.tsv`, `autocro/variants/v0001-*/`, and the `patch.diff` inside. The patch should apply cleanly to the configured `project.root` via `git apply --check`.

### Option B — wire up your real tools

```bash
cp autocro/config.example.yaml autocro/config.yaml
# edit config.yaml:
#   project.root: ".."   # parent project root, relative to autocro/
#   goal.event: "<your conversion event>"
#   adapters.analytics.id: null   # we'll set this in a moment
```

Then in your agent harness, prompt:

> Read `autocro/program.md`. I don't have any adapters yet. Run `autocro/skills/author-adapter.md` to help me write one for my analytics tool, which is `<your tool>`. Here are the API docs: `<url or paste>`.

The agent will copy `adapters/TEMPLATE.md` to `adapters/analytics/<your-tool-id>.md`, fill it in based on your answers, run the `## health` check, and update your `config.yaml`. Repeat for heatmap and abtest adapters as needed. Start with `adapters.abtest.id: null` (plan-only) for safety — the inner loop works perfectly without pushing real experiments.

Once adapters are authored and healthy, prompt:

> Read `autocro/program.md` and begin the inner loop. Run until `budget.max_variants_per_run` or `budget.max_wall_minutes` is hit.

Come back in the morning to `results.tsv` and `variants/RANKED.md`.

## Authoring an adapter

Adapters are **markdown playbooks**, not code. The agent reads them and executes the instructions inline via its normal tool-calling (curl, git, bash, file read/write, optional MCPs — whatever the adapter author specifies in `requires`). A full adapter is typically 50–150 lines.

`adapters/TEMPLATE.md` has the full contract. The minimum you fill in per adapter:

- **`requires`** — env vars, CLI tools, or MCP names your adapter needs.
- **`## health`** — a read-only checklist the agent runs at setup to confirm the adapter works.
- **`## capabilities`** — which methods you implement from the contract (`top_pages`, `funnel`, `page_attention`, `push_variant`, etc.).
- **`## read`** — for each capability, show the exact API call/curl and return the **normalized shape** defined in `adapters/README.md` so the rest of the framework is adapter-blind.
- **`## write`** — (abtest adapters only) how to push a variant as a 0%-allocation experiment.
- **`## idioms`** — short rules for interpreting data from this tool.
- **`## fallbacks`** — how to behave when the API is down; must include `mode: fixture` behavior reading from `fixtures/*.json`.

See `adapters/README.md` for the full contract and `skills/author-adapter.md` for the interactive walk-through.

## Workflow knobs

All three human-control knobs live under `workflow:` in `config.yaml`:

- **`review_mode`** — `"manual"` (default), `"auto"`, or `"off"`.
  - `manual`: every eligible variant is queued to `variants/PENDING.md` with `status: awaiting_review`. Nothing reaches your A/B tool until you either (a) edit the status line in `PENDING.md` to `approved` / `rejected`, or (b) let the agent prompt you interactively during the next inner-loop iteration. Approved variants push at 0% and you ramp manually.
  - `auto`: variants with `composite >= auto_push_threshold` push live immediately at `auto_allocation_pct` traffic (default 50 — an even split with control). Lower-scoring variants still queue into `PENDING.md`. Requires a real abtest adapter.
  - `off`: plan-only. Never touches the A/B tool. Variants still land in `variants/` with scores and a ranked list so you can review them offline.
- **`test_window`** — how long each pushed experiment must run before the outer loop is allowed to declare a winner. Configured in human units (`{value: 2, unit: "weeks"}`). `on_winner` controls what happens next: `queue_followup` (default — seed a follow-up variant from the winning hypothesis), `stop`, or `notify_only`.
- **`auto_apply_to_repo`** — independent from `review_mode`. When true, variants with `composite >= auto_apply_threshold` are `git apply`'d and committed to the parent project's working tree. Orthogonal to the A/B push — a variant can be both auto-committed AND queued for review.

Scheduling (`workflow.schedule`) is for restarting the whole session on an interval and is separate from `test_window`, which governs per-experiment baking time.

## Cadence patterns

`workflow.cadence` is a discoverable preset that documents how you intend to run autocro. The field does not enforce behavior on its own — it tells `setup-check.md` what config bundle to expect, warns if your other settings drift, and informs the README sections you should be reading.

Pick the pattern that matches your traffic + how much active management you want.

### A. `weekly_batch` — recommended at low traffic (< ~50 PV/day)

Run a 10–20 variant batch once a week. All passing variants land in `variants/PENDING.md` ranked by composite. You spend ~15 minutes weekly reviewing the top 3–5 and either commit them to the autocro branch yourself OR tell the agent to push the obvious wins to PostHog.

| Bundle key | Recommended value |
|------------|-------------------|
| `review_mode` | `"manual"` |
| `auto_apply_to_repo` | `false` |
| `schedule.enabled` | `false` (you invoke manually weekly) |
| `budget.max_variants_per_run` | `20` |

**When to pick it.** Your site has too little traffic for any A/B test to reach significance in the `test_window`. The agent's composite score is the practical verdict, not Bayesian confidence. You want to ship CRO patches based on AI judgment + your review, not statistical winners.

**Cost & effort.** ~30–60 min of agent runtime per batch, ~$5–15 in token usage (most of it the 5-pass LLM judge panels). 15 min of human review weekly.

**Risk.** None. Nothing reaches your A/B tool or your working tree without your explicit approval.

### B. `on_demand` (default for fresh setups)

Run autocro only when you ask the agent to. Zero recurring cost. No cron, no nudges. Best for the experimental phase before you've decided whether autocro is worth the weekly cadence.

| Bundle key | Recommended value |
|------------|-------------------|
| `review_mode` | `"manual"` (safest) or `"auto"` |
| `auto_apply_to_repo` | `false` |
| `schedule.enabled` | `false` |
| `budget.max_variants_per_run` | `10` |

**When to pick it.** You're trying autocro for the first time. You want to feel out what the agent produces before committing to a recurring cadence.

**Cost & effort.** Pay-per-run. Zero ambient cost. The downside: easy to forget you have it set up; you'll miss windows where new PostHog data could surface fresh hypotheses.

### C. `scheduled_cron` — best at established traffic (≥ ~100 PV/day)

A cron line restarts autocro every N days/weeks. `setup-check.md` prints the crontab entry; you paste it once into `crontab -e`. The agent runs unattended (e.g. every Sunday 2am) and lands new patches on the autocro branch + new PostHog experiments by morning.

| Bundle key | Recommended value |
|------------|-------------------|
| `review_mode` | `"auto"` |
| `auto_apply_to_repo` | `true` |
| `auto_apply_threshold` | `0.70` or higher (commits go to a dedicated branch) |
| `auto_push_threshold` | `0.60` |
| `schedule.enabled` | `true` (set `interval_value`, `interval_unit`) |
| `budget.max_variants_per_run` | `30` |

**When to pick it.** Your site gets enough traffic that A/B tests can actually reach the `outer_loop.required_significance` gate. You want the framework's full machinery — variants ship, experiments run live, winners get declared, follow-ups get queued — without ongoing human prompting.

**Cost & effort.** ~$15–40/week in token usage depending on `max_variants_per_run`. Human effort drops to monthly review of the autocro branch + the experiment dashboard.

**Risk.** Higher. Patches commit to your repo branch automatically (you decide when to merge). Experiments push live to your A/B tool automatically. Always set `auto_apply_threshold` high (>= 0.70) and keep `config.guardrails.deny_globs` tight.

### Decision matrix

| Question | If yes → |
|----------|----------|
| Is your traffic under ~50 PV/day on conversion-relevant pages? | `weekly_batch` |
| Are you still evaluating whether autocro fits your project? | `on_demand` |
| Do you have ≥ ~100 PV/day AND are you comfortable with autocro committing to a branch automatically? | `scheduled_cron` |
| Do you want maximum experiments per week with minimum management? | `scheduled_cron` |
| Do you want the agent to never touch your repo or your A/B tool without explicit per-variant approval? | `weekly_batch` (or `on_demand` with `review_mode: manual`) |

### Switching cadences later

Cadence is just config — flip it at any time. `setup-check.md` will warn you if the bundle keys (review mode, auto-apply, scheduling) don't match the cadence you've set, but it won't block the run. Migration is a config edit, not a rebuild.

## Project structure

```
autocro/
  README.md                    <- you are here
  program.md                   <- the master skill (the human iterates on this)
  config.example.yaml          <- per-project config template
  config.yaml                  <- your config (gitignored)

  skills/                      <- sub-skills invoked from program.md
    author-adapter.md          <- interactive adapter authoring
    hypothesize.md             <- data → hypotheses
    generate-variant.md        <- hypothesis → patch.diff
    pre-validate.md            <- run composite scoring
    simplicity-review.md       <- diff-size check
    rank.md                    <- re-rank and write RANKED.md
    queue-review.md            <- append to / drain variants/PENDING.md
    read-experiment.md         <- poll real results (outer loop)

  adapters/                    <- tool adapters (markdown playbooks)
    README.md                  <- the contract + normalized shapes
    TEMPLATE.md                <- blank contract to copy
    analytics/{null,fixture}.md
    heatmap/{null,fixture}.md
    abtest/{null,fixture}.md

  harness/
    judge-rubric.md            <- LLM judge rubric (anti-fluff)
    # Phase 2/3 opt-in helpers are NOT yet shipped. Leave the matching
    # prevalidation.lighthouse.enabled / prevalidation.persona.enabled
    # flags false until these exist (or author them yourself):
    #   lighthouse.sh        (Phase 2)
    #   apply-patch.sh       (Phase 2)
    #   make-diff.sh         (Phase 2)
    #   persona-sim.md       (Phase 3)
    #   personas.md          (Phase 3)

  fixtures/
    demo-target/               <- minimal HTML site for offline smoke test
    analytics-sample.json      <- canned data in the normalized shape
    heatmap-sample.json
    experiment-sample.json

  variants/                    <- OUTPUT: generated variants (gitignored)
  variants/PENDING.md          <- OUTPUT: review queue for manual mode
  variants/RANKED.md           <- OUTPUT: current top candidates
  results.tsv                  <- OUTPUT: 14-col append-only log (gitignored)
```

## Design choices

- **One skill to iterate on.** You edit `program.md`, the skills, the adapter template, and the judge rubric. You do not edit the agent's generated output.
- **Nothing baked in.** No tool-specific code ships. Every real integration is authored by the user, per project, via the template and the author-adapter skill.
- **Patch files, not branches.** The agent's output is a `patch.diff` per variant, small and reviewable. Your working tree is never touched unless you explicitly set `guardrails.auto_apply: true`.
- **Predicted vs measured.** `results.tsv` separates pre-validation composite scores (predicted) from real A/B test measurements (measured). The analysis notebook shows a calibration chart so you can catch drift between what the LLM judge loves and what real users actually prefer.
- **NEVER STOP.** Like the original, the inner loop runs until you stop it. Overnight runs produce dozens of ranked variants.

## License

MIT
