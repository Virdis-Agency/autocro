# Adapter: PostHog Heatmap

kind: heatmap
id: posthog

Reference adapter for PostHog's autocapture + session recording features. Uses the same credentials as `adapters/analytics/posthog.md` and the same HogQL query endpoint, but queries `$autocapture`, `$rageclick`, and `$scroll_pct` events. Delivers genuine per-selector click and rage-click data (unlike Microsoft Clarity's aggregate-only API).

Privacy note: this adapter NEVER fetches session recording bodies — only metadata (session id, duration, event count, goal_reached flag). If you want to analyze recording content, do it manually in the PostHog UI.

## requires

```yaml
env:
  - POSTHOG_API_KEY              # same key as adapters/analytics/posthog.md
  - POSTHOG_PROJECT_ID           # same project id
  - POSTHOG_HOST                 # OPTIONAL: same override as analytics/posthog.md
command: [curl, jq]
```

## health

Same as `adapters/analytics/posthog.md` health checks, plus:

4. Verify autocapture events exist: HogQL `SELECT count() FROM events WHERE event = '$autocapture' AND timestamp > now() - interval 7 day` → expect ≥ 0. If 0, autocapture is not enabled for this project; click_map and rage_clicks will return empty and the adapter should still be considered healthy (just degraded).
5. Verify the `$rageclick` event is being captured: same query with `event = '$rageclick'` → ≥ 0 acceptable.

## capabilities

- page_attention: implemented
- click_map: implemented
- rage_clicks: implemented
- session_sample: implemented (metadata only — never recording bodies)

## read

Uses the same `posthog_query` shell helper pattern from `adapters/analytics/posthog.md`.

### page_attention(path)

Query:
```sql
SELECT
  '${path}' AS path,
  quantile(0.5)(properties.$scroll_pct) AS scroll_depth_p50,
  quantile(0.9)(properties.$scroll_pct) AS scroll_depth_p90
FROM events
WHERE event = '$pageview'
  AND properties.$pathname = '${path}'
  AND timestamp > now() - interval 7 day
```

Then a second query for the top 5 clicked elements on this path (becomes `hotspots`):

```sql
SELECT
  properties.$elements_chain AS selector,
  count() / max(count()) OVER () AS intensity
FROM events
WHERE event = '$autocapture'
  AND properties.$current_url LIKE '%${path}%'
  AND timestamp > now() - interval 7 day
GROUP BY selector
ORDER BY intensity DESC
LIMIT 5
```

Transform:
```
hotspots   = array of {selector, intensity} from the second query; intensity is
             normalized 0-1 by dividing by the max count. Elements chain is
             PostHog's serialized CSS-ish path — truncate to the first 80 chars
             for readability, keep the full string for disambiguation.
```

Return:
```jsonc
{"path": "/pricing", "scroll_depth_p50": 0.41, "scroll_depth_p90": 0.74,
 "hotspots": [{"selector": "button.plan-cta.primary", "intensity": 1.0},
              {"selector": "nav a[href='/docs']", "intensity": 0.62}, ...]}
```

### click_map(path, limit=25)

Query:
```sql
SELECT
  properties.$elements_chain AS selector,
  count() AS clicks,
  countIf(event = '$rageclick') / nullif(count(), 0) AS rage_click_rate
FROM events
WHERE event IN ('$autocapture', '$rageclick')
  AND properties.$current_url LIKE '%${path}%'
  AND timestamp > now() - interval 7 day
GROUP BY selector
ORDER BY clicks DESC
LIMIT 25
```

Return:
```jsonc
[{"selector": "button.plan-cta.primary", "clicks": 1240, "rage_click_rate": 0.02},
 {"selector": "nav a[href='/docs']",     "clicks":  980, "rage_click_rate": 0.0}, ...]
```

### rage_clicks(path, limit=25)

Query:
```sql
SELECT
  properties.$elements_chain AS selector,
  count() AS count,
  'users repeatedly clicking this element on ${path}' AS sample_note
FROM events
WHERE event = '$rageclick'
  AND properties.$current_url LIKE '%${path}%'
  AND timestamp > now() - interval 7 day
GROUP BY selector
ORDER BY count DESC
LIMIT 25
```

Return:
```jsonc
[{"selector": "button[disabled]", "count": 62, "sample_note": "users repeatedly clicking this element on /signup"}, ...]
```

### session_sample(path, n=10)

Query (METADATA ONLY — no recording body):
```sql
SELECT
  $session_id AS session_id,
  max(timestamp) - min(timestamp) AS duration_s,
  count() AS events,
  countIf(event = 'sign_up') > 0 AS goal_reached,
  arrayStringConcat(arrayDistinct(groupArray(event)), ', ') AS notable
FROM events
WHERE properties.$pathname = '${path}'
  AND timestamp > now() - interval 7 day
GROUP BY session_id
ORDER BY events DESC
LIMIT ${n}
```

Transform:
```
duration_s: PostHog returns a duration interval; cast to integer seconds.
notable:    truncate the joined event list to 80 chars max.
goal_reached: PostHog returns a boolean; map to JSON bool.
```

Return:
```jsonc
[{"session_id": "s_abc", "duration_s": 142, "events": 47, "goal_reached": false, "notable": "$pageview, $autocapture, $rageclick"}, ...]
```

## idioms

- **`$elements_chain` is PostHog's serialized element path**, not a clean CSS selector. It looks like `button.plan-cta.primary:nth-child(2)` or similar — use it as an identifier but don't try to evaluate it against live DOM.
- **`$scroll_pct` requires session recordings enabled with scroll tracking.** If your project doesn't record sessions (or you've explicitly disabled scroll tracking for privacy), `page_attention` will return 0 for scroll_depth fields. `skills/hypothesize.md` tolerates zeros but downweights them.
- **Session metadata is safe — bodies are not.** The `session_sample` query returns only aggregates. NEVER modify this adapter to pull `snapshot_source` or recording bodies; PostHog session recordings contain PII and the agent should never read them.
- **Rate limit and quota**: HogQL queries count against the same ~240/min limit as the analytics adapter. If you use both analytics and heatmap PostHog adapters in the same iteration, budget ~12 queries per iteration and keep the inner loop under ~20 iterations/hour.
- **Last verified: 2026-04**

## fallbacks

Same as `adapters/analytics/posthog.md`:

- **HTTP 5xx / timeout**: retry once with a narrower window, then return empty arrays / zero-filled object.
- **HTTP 401 / 403**: stop with credentials invalid.
- **HTTP 429**: back off 30s, retry once, return empty.
- **`mode: fixture`**: bypass every live query and read from `autocro/fixtures/heatmap-sample.json`. The fixture is multiplexed by path — demultiplex exactly as `adapters/heatmap/fixture.md` does. This is MANDATORY for `skills/validate-adapter.md`.
