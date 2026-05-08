# Skill: generate-variant

Turn a selected hypothesis into a real, git-applyable patch against the parent project's HEAD, and scaffold the variant folder under `variants/`.

## Inputs

- A single hypothesis object from `skills/hypothesize.md`.
- The parent project's current HEAD (read via the guardrails allowlist).
- `config.guardrails` (deny_globs, max_diff_lines, auto_apply).

## Output

A new directory `autocro/variants/vNNNN-<kebab-slug>/` containing:

- `hypothesis.md` — the full hypothesis, including data citations and predicted lift.
- `patch.diff` — the git-applyable diff against parent HEAD (unified format).
- `sources/` — optional, raw adapter responses that informed the hypothesis (if they exist as files, copy them here; if they were returned inline, dump them as JSON).
- `notes.md` — initial note with the iteration number, research direction, and any sub-variants you considered and rejected.

Do NOT write `pre-validation.json` or `experiment.json` from this skill — those come from `pre-validate.md` and `queue-review.md` (or from the inner-loop auto-mode cascade in `program.md` step 7).

## Slug rules

- Format: `v{iter:04d}-{kebab-case}` where `iter` is the next sequential number past the highest existing `variants/v*/` folder, and `kebab-case` is a 2-5 word slug derived from the hypothesis summary.
- Good: `v0042-pricing-cta-specificity`, `v0043-hero-social-proof`
- Bad: `v42-change`, `variant_42`, `v0042-REPLACE-LEARN-MORE-BUTTON-WITH-START-FREE-TRIAL`

## Patch generation procedure

1. **Read the target files.** Use the guardrails `read_globs` allowlist. If any file you need is not in the allowlist, stop and report the issue in `notes.md` — do NOT expand the allowlist silently.

2. **Check deny_globs mechanically.** Before editing any file, pipe the list of candidate target paths (one per line) through `harness/check_path.py`:

   ```bash
   printf '%s\n' "${target_paths[@]}" \
     | python3 autocro/harness/check_path.py \
         --config-json /tmp/autocro-config.json \
         --variant-slug "${slug}"
   ```

   `/tmp/autocro-config.json` is produced by `skills/setup-check.md` from `config.yaml` via `harness/yaml_to_json.py` and re-used throughout the run. If it doesn't exist, regenerate it from `config.yaml` before calling check_path.

   Exit codes:
   - **0** → all candidate paths are allowed; proceed.
   - **2** → at least one path matched a `deny_glob`. Abort this variant entirely: write `notes.md` with `blocked by deny_glob <path>`, skip `patch.diff`, record `status=discarded` in `results.tsv`, and pick a different hypothesis.
   - **3** → input error (missing config, bad JSON). Stop the whole run — this is a setup bug, not a variant decision.

   Do NOT try to "work around" the deny list by finding a sibling file or renaming — the hypothesis is simply off-limits. Skip it.

3. **No new dependencies.** If the change would require installing a new package (npm, yarn, pip, gem, etc.), abort. Do not edit `package.json`, `requirements.txt`, `Gemfile`, or any lockfile to add dependencies. You may edit these files only to change existing config values (never to add lines).

4. **Generate the patch via `diff -u` — never hand-author hunk headers.** The agent must NOT type `@@ -X,Y +X,Y @@` by hand. Hand-authored unified diffs reliably break `git apply` with `error: patch fragment without header` whenever adjacent hunks share context lines or the agent miscounts by one. The `diff` utility is the single source of truth for hunk math. Procedure, per target file:

   ```bash
   slug="<vNNNN-kebab>"
   path="<path/relative/to/project.root>"
   project_root="<config.project.root>"
   scratch="/tmp/autocro-patchgen/${slug}"

   mkdir -p "${scratch}/$(dirname "${path}")"
   cp "${project_root}/${path}" "${scratch}/${path}.before"
   cp "${project_root}/${path}" "${scratch}/${path}.after"
   # Edit ${scratch}/${path}.after with the proposed change. Use the Edit tool
   # against that scratch file — never against the file under project_root.
   diff -u "${scratch}/${path}.before" "${scratch}/${path}.after" \
     | sed -e "s|^--- ${scratch}/${path}.before.*|--- a/${path}|" \
           -e "s|^+++ ${scratch}/${path}.after.*|+++ b/${path}|" \
     > "${scratch}/${path}.diff"
   ```

   Then assemble the candidate `patch.diff` in scratch by prepending the `diff --git` header for each file and concatenating:

   ```bash
   {
     for path in "${changed_paths[@]}"; do
       printf 'diff --git a/%s b/%s\n' "${path}" "${path}"
       cat "${scratch}/${path}.diff"
     done
   } > "${scratch}/patch.diff"
   ```

   The candidate lives in `${scratch}/patch.diff` until step 8 promotes it into the variant folder. Use real paths relative to the parent project root. The default `diff -u` context (3 lines) is correct.

   Multi-file variants: repeat the cp + edit + diff per file, then concatenate. Do NOT try to merge hunks across files by hand.

   Binary files: not supported. If a hypothesis requires a binary change (image swap, font change), abort the variant and record the reason in `notes.md`.

5. **Verify the patch applies cleanly.** Run `git apply --check` against the scratch patch from inside the parent project root before promoting it:

   ```bash
   ( cd "${project_root}" && git apply --check "${scratch}/patch.diff" )
   ```

   On non-zero exit: write `notes.md` with the exact stderr from `git apply --check`, do NOT promote `${scratch}/patch.diff` to the variant folder, skip `pre-validate.md`, and let the inner loop record `status=crash`. Do NOT attempt to hand-fix hunk headers — re-run step 4 from a fresh scratch directory if the input edit was wrong, otherwise abandon the variant.

5b. **Wrap as experiment (optional, gated by config).** If `config.workflow.patch_shape == "wrapped"`, invoke `skills/wrap-as-experiment.md` with the slug and the scratch patch. That skill rewrites `${scratch}/patch.diff` so the change is gated by a PostHog feature flag (`autocro-<slug>`) rather than shipping unconditionally. It returns one of:

   - `wrapped` → continue with the wrapped patch as `${scratch}/patch.diff`. Re-run `git apply --check` on the rewritten patch (the wrap-as-experiment skill does this internally; trust its result).
   - `passthrough:<reason>` → keep the direct patch as `${scratch}/patch.diff`. Note the reason in `notes.md` (e.g. CSS-only change, non-JSX file). The variant proceeds normally; any PostHog experiment created later for this variant will be a no-op since no code is flag-gated.
   - `aborted:<reason>` → treat exactly like step 5's `git apply --check` failure: write `notes.md` with the abort reason, do NOT promote `${scratch}/patch.diff`, skip `pre-validate.md`, let the inner loop record `status=crash`.

   When `config.workflow.patch_shape != "wrapped"` (the default `"direct"` value, or absent), skip this step entirely.

6. **Count `diff_lines`.** Lines beginning with `+` but not `+++`, plus lines beginning with `-` but not `---`. If `diff_lines > config.guardrails.max_diff_lines`, stop and report the overrun in `notes.md`. Do not truncate the patch — report the overrun so the inner loop can record `status=discarded`.

7. **Sanity self-check.** Before writing `patch.diff`, re-read your proposed diff and confirm:
   - It does not touch any file matching `deny_globs`.
   - It does not add any new dependency.
   - There are no debug statements (`console.log`, `print`, `debugger`) left in.
   - There are no commented-out blocks of old code. Delete cleanly or not at all.
   - The diff is syntactically valid for the target language (balanced braces, closed tags, valid HTML).

   Hunk-header line numbers are NOT a self-check item — `diff -u` produces them and step 5's `git apply --check` is the final arbiter.

8. **Promote the scratch patch and write the variant folder.** Create `autocro/variants/${slug}/`, copy `${scratch}/patch.diff` into it, and write `hypothesis.md` and `notes.md`. Copy any raw adapter responses into `sources/` if they're available as local files. Leave the scratch directory in place — it is the audit trail for how the patch was produced and is cleaned up by the inner loop, not by this skill.

   Reference: a produced `patch.diff` looks like this — do NOT use this as a hand-fill template; it is what step 4's `diff -u` output should resemble after the header rewrite:

   ```
   diff --git a/<path> b/<path>
   --- a/<path>
   +++ b/<path>
   @@ -<old> +<new> @@
   ...
   ```

## hypothesis.md template

```markdown
# v{slug}

**Research direction**: exploit | explore | recombine | focus
**Iteration**: {n}

## Summary

{one-sentence hypothesis}

## Proposed change

{concrete description of what the patch does — file-by-file if it touches multiple}

## Data citations

- `<adapter_id>:<capability>`: {paraphrased data point, e.g. "/pricing has 4120 sessions/week with 0.9% conversion rate; bounce 67%"}
- `<adapter_id>:<capability>`: {second data point if applicable}

## Predicted lift band

{low to high, e.g. "0.3% to 1.2% absolute conversion lift on /pricing"}

## Reasoning

{2-4 sentences connecting the cited data to the proposed change, referencing
judge rubric items where relevant. Explicitly say why THIS change rather than
a larger or smaller one.}

## Simplicity rationale

{why this is the right size of change — what was rejected as too small or too large}
```

## notes.md template

```markdown
# Notes for v{slug}

- Iteration: {n}
- Research direction: {exploit | explore | recombine | focus}
- Rejected sub-variants considered this iteration:
  - "{rejected alternative 1}" — {one-line reason}
  - "{rejected alternative 2}" — {one-line reason}
```

## Failure modes and how to report them

If generation fails, still create the variant folder and `notes.md`, but omit `patch.diff`. The inner loop will see the missing patch and record `status=crash`.

- **Patch would touch deny_glob**: notes.md says "blocked by deny_glob <path>"; do not write patch.diff.
- **Patch would add dependency**: notes.md says "blocked: requires new dep <name>"; do not write patch.diff.
- **Patch exceeds max_diff_lines**: STILL write patch.diff so the inner loop's simplicity-review.md can log the exact count; notes.md says "oversized: {n} lines".
- **Target file not in read_globs allowlist**: notes.md says "blocked: <path> outside read_globs"; do not write patch.diff.
- **`git apply --check` failed in step 5**: do NOT promote `${scratch}/patch.diff` to the variant folder. Create the variant folder with `notes.md` only (saying "patch apply failed: <stderr from git apply --check>") and leave `patch.diff` absent — the inner loop's missing-patch handler records `status=crash`. The scratch patch stays under `/tmp/autocro-patchgen/${slug}/` for the human to inspect. Do not hand-edit hunk headers; the diff was generated by `diff -u` and any failure here means the scratch edit was wrong (e.g. edited the `.before` file by mistake, or the source file changed under us).

## Do not

- Do not apply the patch to the parent's working tree. Patches live in `variants/` and are applied only by `pre-validate.md` in an out-of-tree worktree at `~/.cache/autocro/worktrees/<slug>/`, and only if `auto_apply: true` or Lighthouse is enabled.
- Do not edit `autocro/program.md`, any file under `autocro/skills/`, any file under `autocro/adapters/`, or any file under `autocro/harness/`. Those are the human-iterated skill.
- Do not edit `autocro/results.tsv` from this skill. Only the inner loop itself writes rows.
