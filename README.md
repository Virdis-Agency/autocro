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

- **Claude Code** (or any compatible harness that can run `curl`, `git`, `python3`, `jq`, file I/O, and optional MCP tools from inside a markdown playbook). This is what executes `program.md`, the skills, and the adapter playbooks.
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
`autocro/config.yaml`. Do NOT open Claude Code from inside the clone root;
every skill hardcodes `autocro/...` paths and they will not resolve.

Then open Claude Code in your project root and prompt:

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

Then in Claude Code, prompt:

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
