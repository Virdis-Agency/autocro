# Adapter: PostHog Analytics

kind: analytics
id: posthog

Reference adapter for [PostHog](https://posthog.com) — uses HogQL queries against the `events` table to return all six normalized analytics capabilities in one coherent shape. PostHog is the one reference tool that covers all three kinds (analytics, heatmap, abtest) with the same credentials — see also `adapters/heatmap/posthog.md` and `adapters/abtest/posthog.md`.

## requires

```yaml
env:
  - POSTHOG_API_KEY              # personal API key with "Query" + "Read" project scopes, from posthog.com/settings/user-api-keys
  - POSTHOG_PROJECT_ID           # numeric project id (not the "team" api key) from posthog.com/settings/project
  - POSTHOG_HOST                 # OPTIONAL: https://us.posthog.com (default), https://eu.posthog.com, or self-hosted URL
command: [curl, jq]
```

## health

1. `curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $POSTHOG_API_KEY" "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/"` → expect HTTP 200.
2. HogQL smoke test:
   ```bash
   curl -sS -X POST -H "Authorization: Bearer $POSTHOG_API_KEY" -H "Content-Type: application/json" \
     "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/query" \
     -d '{"query": {"kind": "HogQLQuery", "query": "SELECT 1"}}' | jq '.results[0][0]'
   ```
   → expect `1`.
3. Verify `$pageview` events exist: same endpoint with `"query": "SELECT count() FROM events WHERE event = '\\$pageview' AND timestamp > now() - interval 7 day"` → expect an integer ≥ 0. Zero is acceptable on new projects.
4. If HTTP 401 / 403: stop with `credentials invalid for POSTHOG_API_KEY — regenerate at $POSTHOG_HOST/settings/user-api-keys and give it Query + Read scopes on the project`.

## capabilities

- top_pages: implemented
- landing_pages: implemented
- funnel: implemented
- traffic_sources: implemented
- conversions: implemented
- session_quality: implemented

## read

All six capabilities hit the same HogQL query endpoint. The shared helper pattern:

```bash
posthog_query() {
  local q="$1"
  curl -sS -X POST \
    -H "Authorization: Bearer $POSTHOG_API_KEY" \
    -H "Content-Type: application/json" \
    "${POSTHOG_HOST:-https://us.posthog.com}/api/projects/$POSTHOG_PROJECT_ID/query" \
    -d "{\"query\": {\"kind\": \"HogQLQuery\", \"query\": \"$q\"}}"
}
```

HogQL requires escaping the `$` in event names as `\\$pageview` when embedded in a JSON string.

### top_pages(window="7d", limit=25)

Query:
```sql
SELECT
  properties.$pathname AS path,
  count() AS sessions,
  countIf(properties.$session_duration < 5) / count() AS bounce_rate,
  countIf(event = 'sign_up') / count() AS conv_rate,
  avg(properties.$session_duration) AS avg_time_s
FROM events
WHERE event = '$pageview'
  AND timestamp > now() - interval 7 day
  AND properties.$pathname IS NOT NULL
GROUP BY path
ORDER BY sessions DESC
LIMIT 25
```

Transform: the `results` array comes back as rows of `[path, sessions, bounce_rate, conv_rate, avg_time_s]`. Convert to array of objects with those keys. Numbers come out as floats — cast `sessions` to integer.

Return:
```jsonc
[{"path": "/pricing", "sessions": 12340, "bounce_rate": 0.61, "conv_rate": 0.018, "avg_time_s": 42}, ...]
```

### landing_pages(window="7d", limit=25)

Query:
```sql
SELECT
  argMin(properties.$pathname, timestamp) AS path,
  count(DISTINCT $session_id) AS landings,
  countIf(properties.$session_duration < 5) / count() AS bounce_rate,
  countIf(event = 'sign_up') / count(DISTINCT $session_id) AS conv_rate
FROM events
WHERE event = '$pageview'
  AND timestamp > now() - interval 7 day
GROUP BY $session_id
LIMIT 25
```

Return:
```jsonc
[{"path": "/pricing", "landings": 8420, "bounce_rate": 0.68, "conv_rate": 0.012}, ...]
```

### funnel(steps)

Use PostHog's Funnel query (an insight type) instead of raw HogQL — funnels are a first-class concept.

```bash
posthog_query '{"kind": "FunnelsQuery", "series": [
  {"kind": "EventsNode", "event": "$pageview", "properties": [{"key": "$pathname", "value": "/"}]},
  {"kind": "EventsNode", "event": "$pageview", "properties": [{"key": "$pathname", "value": "/pricing"}]},
  {"kind": "EventsNode", "event": "sign_up"}
]}'
```

Transform: the response gives per-step `count`. Map to `{step, entered, advanced}` where `advanced` is the next step's `count`.

Return:
```jsonc
[{"step": "landing", "entered": 10000, "advanced": 6200},
 {"step": "pricing", "entered": 6200, "advanced": 980},
 {"step": "signup",  "entered": 980,  "advanced": 410}]
```

### traffic_sources(window="7d", limit=25)

Query:
```sql
SELECT
  properties.$referring_domain AS source,
  'referral' AS medium,
  count(DISTINCT $session_id) AS sessions,
  countIf(event = 'sign_up') / count(DISTINCT $session_id) AS conv_rate
FROM events
WHERE timestamp > now() - interval 7 day
  AND properties.$referring_domain IS NOT NULL
GROUP BY source
ORDER BY sessions DESC
LIMIT 25
```

Return:
```jsonc
[{"source": "google.com", "medium": "referral", "sessions": 5200, "conv_rate": 0.021}, ...]
```

### conversions(event, window="7d")

Query:
```sql
SELECT
  '${event}' AS event,
  countIf(event = '${event}') AS count,
  count(DISTINCT $session_id) AS sessions,
  countIf(event = '${event}') / count(DISTINCT $session_id) AS rate
FROM events
WHERE timestamp > now() - interval 7 day
```

Return:
```jsonc
{"event": "sign_up", "count": 410, "sessions": 12340, "rate": 0.0332}
```

### session_quality(path, window="7d")

Query:
```sql
SELECT
  '${path}' AS path,
  avg(properties.$session_duration) AS avg_time_s,
  avg(properties.$scroll_pct) AS scroll_depth_p50,
  countIf(properties.$session_duration < 5) / count() AS bounce_rate,
  avg(properties.$engagement_score) AS engagement_score
FROM events
WHERE event = '$pageview'
  AND properties.$pathname = '${path}'
  AND timestamp > now() - interval 7 day
```

Note: `$scroll_pct` and `$engagement_score` are only present if you enable session recordings and scroll depth tracking in your PostHog settings. If either is null, substitute 0 in the Transform step — the schema allows 0-1 inclusive.

Return:
```jsonc
{"path": "/pricing", "avg_time_s": 42, "scroll_depth_p50": 0.48, "bounce_rate": 0.61, "engagement_score": 0.33}
```

## idioms

- **HogQL is PostHog's SQL dialect.** The `$` in property names is literal (e.g. `$pathname`, `$session_id`); escape it as `\\$` when embedded in JSON bodies.
- **`$session_duration`, `$scroll_pct`, and `$engagement_score` are optional** — they require enabling session recordings and specific feature flags in PostHog settings. If your project doesn't have them, `session_quality` will return 0 for those fields. `skills/hypothesize.md` tolerates 0 but downweights data citations that lean on obviously-empty metrics.
- **Timezone.** All PostHog timestamps are UTC. `now() - interval 7 day` is server-side UTC.
- **Rate limit**: ~240 query req/min per workspace on PostHog cloud. HogQL queries are expensive; keep the inner loop's query count per iteration below ~10.
- **`POSTHOG_PROJECT_ID` is the numeric project id, not the project API key.** Users frequently confuse these — the project id is visible at `$POSTHOG_HOST/settings/project` under "Project variables" > "Project ID".
- **Last verified: 2026-04**

## fallbacks

- **HTTP 5xx / transient**: retry once with `interval 1 day` instead of 7, then return `[]` / zero-filled object.
- **HTTP 401 / 403**: stop with `credentials invalid for POSTHOG_API_KEY`.
- **HTTP 429 (rate limit)**: back off 30s, retry once, return empty on second failure.
- **Query timeout (HTTP 504)**: narrow the window (e.g. `interval 1 day`) and retry once. If it times out again, mark the capability degraded for this iteration and return empty.
- **`mode: fixture`**: bypass all live queries and read from `autocro/fixtures/analytics-sample.json`. For each capability, return the pre-shaped slice exactly as `adapters/analytics/fixture.md` does. This is MANDATORY so `skills/validate-adapter.md` can run without PostHog credentials or burning query quota.
