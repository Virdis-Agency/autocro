# Adapter: Microsoft Clarity

kind: heatmap
id: clarity

Reference adapter for [Microsoft Clarity](https://clarity.microsoft.com) via the [Data Export API](https://learn.microsoft.com/en-us/clarity/setup-and-installation/clarity-data-export-api). Clarity is free, privacy-respecting, and widely used — but its public API is **aggregate-only**: it returns per-URL rollups (scroll depth, rage click counts, dead click counts) but does NOT expose per-selector click data or session recording metadata. Only `page_attention` can be genuinely implemented from this API; the other heatmap capabilities are marked `not_implemented` with an explanation rather than faking a single-selector response.

If you need per-selector click maps or session sample metadata, use the PostHog heatmap adapter (`adapters/heatmap/posthog.md`) or author one for Hotjar.

## requires

```yaml
env:
  - CLARITY_PROJECT_ID           # Clarity project ID (UUID-like string from clarity.microsoft.com settings)
  - CLARITY_API_TOKEN            # API token with Data Export scope from clarity.microsoft.com/api-keys
command: [curl, jq]
```

## health

1. `curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $CLARITY_API_TOKEN" "https://www.clarity.ms/export-data/api/v1/project-live-insights?numOfDays=1&dimension1=URL"` → expect HTTP 200.
2. The same call parsed: `jq 'length'` → expect an array (possibly empty on quiet days; that is acceptable).
3. If HTTP 401 / 403: stop with `credentials invalid for CLARITY_API_TOKEN — regenerate at clarity.microsoft.com/api-keys`.
4. If HTTP 429: the daily quota is already burned (see ## idioms — the free tier caps at ~10 requests/day). Fall back to `mode: fixture` and log a warning so the loop can still run without Clarity data today.

## capabilities

- page_attention: implemented
- click_map: not_implemented (Clarity Data Export API does not expose per-selector click counts)
- rage_clicks: not_implemented (Clarity returns per-URL rage click aggregates but not per-selector; marking as not_implemented is more honest than faking a single-element "(aggregate)" selector)
- session_sample: not_implemented (API has no session recording metadata endpoint)

## read

### page_attention(path)

Clarity's Data Export returns a single response with metrics across many URLs. We pull the metric set once (costs 1 quota unit) and filter to the requested `path` locally — it is cheaper than making N calls for N target paths.

Call:
```bash
curl -sS -H "Authorization: Bearer $CLARITY_API_TOKEN" \
  "https://www.clarity.ms/export-data/api/v1/project-live-insights?numOfDays=3&dimension1=URL"
```

Transform:
```
raw shape (abridged):
  [
    {"metricName": "Traffic",           "information": [{"URL": "/pricing", "totalSessionCount": "820", "totalBotSessionCount": "14"}, ...]},
    {"metricName": "ScrollDepth",       "information": [{"URL": "/pricing", "averageScrollDepth": "41.3"}, ...]},
    {"metricName": "EngagementTime",    "information": [{"URL": "/pricing", "averageEngagementTime": "52.1"}, ...]}
  ]

find the entries where `URL == path` across the three metric blocks. Then:
  scroll_depth_p50 = Clarity's averageScrollDepth / 100   (Clarity returns percent, contract is 0-1)
  scroll_depth_p90 = 0                                     (API does NOT expose percentiles; fill 0 and note in hypothesis.md;
                                                            hypothesize.md tolerates 0 for this field but may discount the data citation)
  hotspots         = []                                    (API does NOT expose per-element intensity; empty array is valid)
```

Return:
```jsonc
{"path": "/pricing", "scroll_depth_p50": 0.413, "scroll_depth_p90": 0.0, "hotspots": []}
```

## idioms

- **Data Export API quota is ~10 requests/day per project on the free tier** (and ~100/day on the paid tier — check the latest numbers at the Clarity docs link above; Microsoft has been known to change them). Because of this, `skills/validate-adapter.md` is configured to run live validation **only immediately after authoring** and otherwise runs exclusively in `mode: fixture`. One full validation call today costs 1 quota unit; a single inner-loop iteration that hits `page_attention` for every target path also costs 1 quota unit (we pull all URLs in one call and filter locally).
- **`numOfDays` accepts 1, 2, or 3 only.** Contract `window="28d"` maps to `numOfDays=3` — Clarity's API simply cannot look further back.
- **Percent vs fraction.** Clarity returns `averageScrollDepth` as a percent (0-100). The Transform divides by 100 to match the 0-1 contract. Same for bounce_rate style fields.
- **No hotspot selector data.** The Data Export API is aggregate-only. `hotspots` is always `[]`. Users who need real selector-level heat maps should look at the PostHog heatmap adapter or author a Hotjar adapter.
- **`path` matching.** Clarity stores the full URL path including query string in `URL`. The adapter matches on `path` via exact equality after stripping the query string (everything after `?`). If your paths use unusual encoding (Unicode, double slashes), test in fixture mode first.
- **Last verified: 2026-04**

## fallbacks

- **HTTP 5xx / transient failure**: retry once with `numOfDays=1`, then return the empty `page_attention` shape (`{"path": path, "scroll_depth_p50": 0, "scroll_depth_p90": 0, "hotspots": []}`) and log a warning.
- **HTTP 401 / 403**: stop immediately with `credentials invalid for CLARITY_API_TOKEN`.
- **HTTP 429 (quota burned)**: flip the in-memory mode flag to `fixture` for the rest of the run and log a prominent warning to `run.log` (event: `adapter_validate_fail` with notes `clarity quota hit, switched to fixture for this run`). Do NOT retry during the run.
- **`mode: fixture`**: bypass the live call and read the pre-shaped `page_attention` slice from `autocro/fixtures/heatmap-sample.json`. The fixture file is an array keyed across multiple paths — find the entry where `.path == path` and return it. If no entry matches, return `{"path": path, "scroll_depth_p50": 0, "scroll_depth_p90": 0, "hotspots": []}`. This is MANDATORY for `skills/validate-adapter.md` to exercise the adapter without burning quota.
