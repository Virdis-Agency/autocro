# Skill: wrap-as-experiment

Transform a generated direct patch into a flag-gated A/B-test-shaped patch so that PostHog (or any feature-flag tool) can actually serve a treatment differential to control vs treatment users. Without this transformation, `adapters/abtest/posthog.md::push_variant` creates a feature flag and an experiment object, but the patched code ships to 100% of users — there is no real A/B comparison.

Invoked from `skills/generate-variant.md` (between its `git apply --check` step and the diff-lines count step) when `config.workflow.patch_shape == "wrapped"`. Never invoked directly by `program.md`.

## Why this exists

The default direct patch produced by `skills/generate-variant.md` looks like:

```diff
-<button type="submit" class="btn btn-submit" disabled>Submit</button>
+<button type="submit" class="btn btn-submit">Submit</button>
```

If that patch is committed to the parent project, every visitor sees the new button — there is no control group. The PostHog feature flag created by `push_variant` flips at 50% allocation, but both sides of the flip see identical markup. The "experiment" measures nothing.

The wrapped patch produced by this skill instead looks like (abridged):

```diff
+import { useFeatureFlagVariantKey } from 'posthog-js/react'
 ...
 export function SignupForm() {
+  const autocroVariant = useFeatureFlagVariantKey('autocro-v0001-enable-signup-submit')
   return (
     <form action="/signup" method="post">
       ...
-      <button type="submit" class="btn btn-submit" disabled>Submit</button>
+      {autocroVariant === 'treatment' ? (
+        <button type="submit" class="btn btn-submit">Submit</button>
+      ) : (
+        <button type="submit" class="btn btn-submit" disabled>Submit</button>
+      )}
     </form>
   )
 }
```

Now PostHog's flag genuinely gates two code paths. Users in the `treatment` bucket see the working button; users in `control` see the disabled one. The experiment can measure conversion lift.

## Preconditions (one-time setup the human does once per parent project)

This skill assumes the parent project has these in place. If absent, the skill aborts the variant with a clear note and the human handles the precondition between runs.

1. **`posthog-js` is a runtime dependency.** Verified via `package.json`. virdis has `posthog-js@^1.372.10` ✓.
2. **PostHog is initialized at app startup.** virdis has this in `instrumentation-client.ts:6` ✓.
3. **`PostHogProvider` wraps the app tree** so React hooks like `useFeatureFlagVariantKey` work. This is the one piece virdis does NOT yet have. The human adds it once to `app/providers.tsx` (or directly inside `app/layout.tsx`):

   ```tsx
   'use client'
   import posthog from 'posthog-js'
   import { PostHogProvider } from 'posthog-js/react'

   export function PostHogClientProvider({ children }: { children: React.ReactNode }) {
     return <PostHogProvider client={posthog}>{children}</PostHogProvider>
   }
   ```

   Then in `app/layout.tsx`, wrap `{children}` in `<PostHogClientProvider>`. One-time, ~10 lines.

If precondition 1 or 2 is missing, this skill aborts every variant. If precondition 3 is missing, the wrapped patch will compile but `useFeatureFlagVariantKey` returns `undefined` for every visitor, so every visitor sees the control branch — degenerate but not broken. Document this in `notes.md` so the human can add the provider when they're ready.

## Inputs

- The slug from `skills/generate-variant.md` (e.g. `v0042-pricing-cta-specificity`).
- The scratch direct patch at `/tmp/autocro-patchgen/<slug>/patch.diff`.
- The list of file paths the patch modifies.
- The parent project's source files (read-only, per `config.guardrails.read_globs`).
- `config.project.stack` (this skill currently supports `nextjs` only — see "Stack support" below).

## Output

- A rewritten scratch patch at `/tmp/autocro-patchgen/<slug>/patch.diff` (in place — overwrites the direct patch).
- A note appended to the variant's `notes.md` recording the wrapping decision (whether wrapping happened, what scope was wrapped, what aborted).
- Return value to `generate-variant.md`: `wrapped` | `aborted:<reason>` | `passthrough:<reason>`.

`aborted` means abandon the variant entirely (status=discarded). `passthrough` means the direct patch is fine as-is (e.g., for a CSS-only change that can't be wrapped); the inner loop proceeds with the direct patch and the variant is auto-applied to the branch but no PostHog experiment will be created (or one will be created but be a no-op — flag this in `notes.md`).

## Stack support

The wrapping logic is framework-specific because the wrapper API differs across stacks. v1 of this skill supports:

- **`nextjs`** (App Router or Pages Router). Wraps JSX expressions inside Client Components. Aborts on Server Components.

Out of scope for v1 (abort with `aborted:unsupported_stack`):
- `nuxt`, `astro`, `sveltekit`, `remix`, `rails`, `django`, `wordpress`, `plain-html`.

When the human needs another stack, extend this skill with the equivalent wrapper pattern (e.g. for Astro, a client-side script that swaps DOM after `posthog.onFeatureFlags`; for Rails, a server-side `if posthog_flag(...)` ERB conditional). Each stack adds a new section here.

## Decision tree (per modified file)

For each file path the direct patch modifies, run this decision tree before attempting to wrap. Stop at the first node that fires.

```
1. Is the file a JSX/TSX file (.jsx, .tsx)?
   NO  -> passthrough:non_jsx (CSS, JSON, MDX, plain HTML — cannot wrap with React hook).
          The direct patch ships as-is. PostHog experiment will be created but is a no-op.
          Note in notes.md: "non-JSX file; ships unflagged".
   YES -> continue.

2. Is the file in app/ (Next.js App Router) AND missing a top-of-file 'use client' directive?
   YES -> aborted:server_component (hooks unavailable in Server Components).
          notes.md: "abort: <path> is a Server Component; hook-based wrapping needs 'use client'.
                     Convert manually or skip this hypothesis."
   NO  -> continue.

3. Is the file in pages/ (Next.js Pages Router)?
   YES -> continue (Pages Router files are always client-rendered React).
   NO  -> continue.

4. Does the changed region sit inside a JSX expression (i.e. inside a return statement
   or an inline expression that React will render)?
   NO  -> The change is to imports, types, exports, or non-render code.
          aborted:non_render_change. notes.md: "abort: change is outside JSX render path
          (likely an import/type edit) — wrapping not meaningful."
   YES -> continue to "Wrapping procedure" below.
```

## Wrapping procedure

Run once per modified JSX/TSX file that passed the decision tree.

### Step W1: Find the smallest enclosing JSX expression around the change

Read the file content (the `.before` version from the scratch dir). Locate the line numbers the patch's hunks touch. Walk outward from each hunk to find the smallest contiguous JSX expression that fully encloses every changed line. "Smallest enclosing JSX expression" means:

- Prefer a single JSX element (`<button ...>...</button>`) over a fragment.
- Prefer one element over a group of sibling elements.
- If the change is to a single attribute on an element, the wrappable scope is the whole element (you cannot conditionally include/exclude an attribute without re-rendering the element).
- If the change spans multiple sibling elements, wrap their common parent expression (or wrap them both together inside a fragment `<>...</>`).
- If the change is inside a `.map()` callback, wrap the JSX returned by the callback — not the whole `.map()` call.
- If the change is inside a conditional expression (existing ternary or `&&`), wrap the JSX of the branch that changes.

If you cannot identify a clean wrappable scope (e.g. the change is structural enough that wrapping would require changing the function signature), `aborted:unwrappable_scope` and stop.

### Step W2: Identify the enclosing function component

Walk outward from the wrappable scope to find the nearest enclosing function or arrow-function React component. That function is where the `useFeatureFlagVariantKey` hook call goes. Hook calls must be at the top level of a component body (React rules of hooks).

If the wrappable scope is inside a map callback that is itself inside a component body, the hook still goes in the component body (not in the callback) — capture the variant value once and reference it inside the callback.

### Step W3: Synthesize the wrapped JSX

Using the `.before` file content as the basis (NOT the `.after` content from the direct patch), produce a `.after` file that:

1. **Adds the import** at the top of the file (after any existing imports), if not already present:
   ```tsx
   import { useFeatureFlagVariantKey } from 'posthog-js/react'
   ```
   If the import is already present (e.g. another autocro variant in the same file already added it), skip this addition.

2. **Adds the hook call** as the first line inside the component body:
   ```tsx
   const autocroVariant_<slug_short> = useFeatureFlagVariantKey('autocro-<slug>')
   ```
   `<slug_short>` is the slug with the `vNNNN-` prefix stripped and hyphens converted to underscores, truncated to 40 chars. Example: slug `v0042-pricing-cta-specificity` → variable `autocroVariant_pricing_cta_specificity`. This avoids collisions when multiple variants stack in the same file.

   If a hook call for the same flag key already exists in the file (from a previous wrap), reuse it — do not add a duplicate.

3. **Replaces the wrappable scope** with a conditional expression:
   ```tsx
   {autocroVariant_<slug_short> === 'treatment' ? (
     <TreatmentJSX />
   ) : (
     <ControlJSX />
   )}
   ```
   `<ControlJSX />` is the original wrappable scope from `.before` (verbatim).
   `<TreatmentJSX />` is the wrappable scope after applying the direct-patch change to it (verbatim).

   If the wrappable scope is at the top level of a `return` statement, you may collapse the curly-brace wrap into the return:
   ```tsx
   return autocroVariant_<slug_short> === 'treatment' ? (
     <TreatmentJSX />
   ) : (
     <ControlJSX />
   )
   ```

4. **Preserves indentation** of the surrounding code. The wrap adds two indent levels around the original; respect the file's existing indent style (tabs vs spaces, width).

### Step W4: Regenerate the patch via `diff -u`

This is identical to step 4 of `skills/generate-variant.md` — use `diff -u` (or Python's `difflib.unified_diff`), do NOT hand-author hunk headers. Overwrite `/tmp/autocro-patchgen/<slug>/patch.diff` with the new wrapped patch.

If the patch modifies multiple files, regenerate each file's diff independently and concatenate exactly as `generate-variant.md` step 4 does.

### Step W5: Re-validate `git apply --check`

```bash
( cd "${project_root}" && git apply --check "/tmp/autocro-patchgen/${slug}/patch.diff" )
```

On non-zero exit: `aborted:wrapped_patch_invalid`. notes.md: "abort: wrapped patch failed git apply --check: <stderr>". Leave the scratch directory in place for the human to inspect.

### Step W6: Update notes.md

Append a `## wrap-as-experiment` block to the variant's `notes.md`:

```markdown
## wrap-as-experiment
decision: wrapped
flag_key: autocro-<slug>
files_wrapped:
  - <path>: scope=<button ...>, hook_var=autocroVariant_<slug_short>
hook_added: true | false (false means another wrap in this file already added it)
import_added: true | false
control_branch: original markup (the existing user behavior)
treatment_branch: patched markup (what the hypothesis tests)
posthog_provider_required: true (see preconditions in skills/wrap-as-experiment.md)
```

If decision is `aborted` or `passthrough`, write that instead with the reason field.

## Failure modes — abort behavior

When this skill returns `aborted:<reason>`, `skills/generate-variant.md` MUST:
1. Leave the variant folder in place with `notes.md` (no `patch.diff`).
2. Let the inner loop record `status=discarded` (per program.md step 7 base classification — wrapping abort is treated like the existing failure modes in `generate-variant.md` "Failure modes" section).

When this skill returns `passthrough:<reason>`, `skills/generate-variant.md` MUST:
1. Keep the direct patch as `patch.diff`.
2. Continue normally through the rest of generate-variant.md and pre-validate.md.
3. The inner loop will treat this variant normally — auto-apply if composite is high enough, push to PostHog if review_mode is auto. The PostHog experiment will be a no-op (flag set, no code gated) but the auto-applied patch will still ship the change.
4. Record the passthrough reason in `notes.md`.

## What this skill must NOT do

- **Do NOT install or modify dependencies.** The `posthog-js/react` import must already resolve. If the parent project lacks `posthog-js`, abort every variant — do not add it to `package.json`.
- **Do NOT modify `package.json`, `tsconfig.json`, or any build config** to make the wrapper compile.
- **Do NOT add a `'use client'` directive** to a Server Component automatically. Converting a Server Component to a Client Component has performance implications the human should make consciously. Abort and let the human decide.
- **Do NOT touch `instrumentation-client.ts`** (covered by deny_globs anyway).
- **Do NOT create a new shared component file** like `components/experiments/ExperimentSwitch.tsx`. Inlining the hook call is intentionally chosen so each variant patch is self-contained and does not depend on cross-cutting infrastructure that may or may not exist.
- **Do NOT modify the hypothesis.md or pre-validation.json.** This skill only transforms the patch.

## Future extensions (out of scope for v1)

- **Cleanup skill**: a companion `skills/unwrap-experiment.md` that, after a winner is declared by the outer loop, rewrites the file to keep only the winning branch and removes the hook + import.
- **Shared `<ExperimentSwitch>` helper**: once the human has 5+ wrapped variants in the codebase, the boilerplate becomes worth extracting. Create `components/experiments/ExperimentSwitch.tsx` with the hook + ternary, then update this skill to use `<ExperimentSwitch flag="autocro-<slug>" control={...} treatment={...} />` instead of the inline pattern.
- **SSR-safe variant via cookie**: PostHog flags load asynchronously, so the first paint always shows control. For experiments where the first-paint behavior matters, server-render with the variant determined from a PostHog-set cookie. Adds complexity; defer until needed.
- **Stack support beyond Next.js**: see "Stack support" above.
