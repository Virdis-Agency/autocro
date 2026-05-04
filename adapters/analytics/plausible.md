# Adapter: Plausible Analytics

kind: analytics
id: plausible

Reference adapter for [Plausible Analytics](https://plausible.io). Reads page views, landing pages, traffic sources, and goal conversions from the Plausible Stats API. Plausible is a privacy-first analytics tool: data is coarser than GA4 (no fine-grained session quality, no funnels), but the API is simple and the shape maps cleanly to the normalized contract.

## requires

```yaml
env:
  - PLAUSIBLE_API_KEY            # personal API token with Stats API scope
  - PLAUSIBLE_SITE_ID            # the domain registered in Plausible (e.g. "acme.com")
  - PLAUSIBLE_BASE_URL           # OPTIONAL: override for self-hosted instances (default: https://plausible.io)
command: [curl, jq]
```

## health

1. `curl -sS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $PLAUSIBLE_API_KEY" "${PLAUSIBLE_BASE_URL:-https://plausible.io}/api/v1/stats/aggregate?site_id=$PLAUSIBLE_SITE_ID&period=7d&metrics=visitors"` → expect HTTP 200.
2. The same call parsed as JSON: `jq '.results.visitors.value'` → expect an integer (may be 0 on new sites, that's fine).
3. If HTTP 401 or 403: the env var `PLAUSIBLE_API_KEY` is missing scope; stop with "credentials invalid for PLAUSIBLE_API_KEY — give it Stats API scope in plausible.io/settings/api-keys".

## capabilities

- top_pages: implemented
- landing_pages: implemented
- funnel: not_implemented (Plausible does not expose funnel endpoints on the public Stats API)
- traffic_sources: implemented
- conversions: implemented
- session_quality: not_implemented (Plausible's privacy model does not expose per-session scroll / engagement scores)

## read

### top_pages(window="7d", limit=25)

Call:
```bash
curl -sS -H "Authorization: Bearer $PLAUSIBLE_API_KEY" \
  "${PLAUSIBLE_BASE_URL:-https://plausible.io}/api/v1/stats/breakdown?site_id=$PLAUSIBLE_SITE_ID&period=${window}&property=event:page&metrics=visitors,bounce_rate,visit_duration&limit=${limit}"
```

Transform:
```
raw shape:
  {"results": [{"page": "/x", "visitors": 1234, "bounce_rate": 61, "visit_duration": 42.3}, ...]}

normalized shape:
  for each row:
    path        = .page
    sessions    = .visitors             (Plausible uses "visitors" for unique-ish sessions)
    bounce_rate = .bounce_rate / 100    (Plausible returns percent 0-100, contract is 0-1)
    conv_rate   = 0                     (see ## idioms — per-page conv_rate requires N+1 goal calls;
                                         omitted in this adapter to keep it one-call-per-capability)
    avg_time_s  = .visit_duration
```

Return:
```jsonc
[{"path": "/pricing", "sessions": 1234, "bounce_rate": 0.61, "conv_rate": 0.0, "avg_time_s": 42.3}, ...]
```

### landing_pages(window="7d", limit=25)

Call:
```bash
curl -sS -H "Authorization: Bearer $PLAUSIBLE_API_KEY" \
  "${PLAUSIBLE_BASE_URL:-https://plausible.io}/api/v1/stats/breakdown?site_id=$PLAUSIBLE_SITE_ID&period=${window}&property=visit:entry_page&metrics=visitors,bounce_rate&limit=${limit}"
```

Transform:
```
for each row:
  path        = .entry_page
  landings    = .visitors               (entry-page "visitors" == landings in Plausible terms)
  bounce_rate = .bounce_rate / 100
  conv_rate   = 0                       (same caveat as top_pages)
```

Return:
```jsonc
[{"path": "/pricing", "landings": 820, "bounce_rate": 0.64, "conv_rate": 0.0}, ...]
```

### traffic_sources(window="7d", limit=25)

Call:
```bash
curl -sS -H "Authorization: Bearer $PLAUSIBLE_API_KEY" \
  "${PLAUSIBLE_BASE_URL:-https://plausible.io}/api/v1/stats/breakdown?site_id=$PLAUSIBLE_SITE_ID&period=${window}&property=visit:source&metrics=visitors&limit=${limit}"
```

Transform:
```
for each row:
  source    = .source
  medium    = "referral"                (Plausible source is domain-like; map everything to "referral"
                                         except "Direct / None" which becomes medium="direct", source="direct")
  sessions  = .visitors
  conv_rate = 0                         (per-source conv_rate needs an N+1 goal call chain; omitted)
```

Return:
```jsonc
[{"source": "google.com", "medium": "referral", "sessions": 5200, "conv_rate": 0.0}, ...]
```

### conversions(event, window="7d")

Two calls: one for total sessions in the window, one for the goal-filtered event count.

Call:
```bash
SESSIONS=$(curl -sS -H "Authorization: Bearer $PLAUSIBLE_API_KEY" \
  "${PLAUSIBLE_BASE_URL:-https://plausible.io}/api/v1/stats/aggregate?site_id=$PLAUSIBLE_SITE_ID&period=${window}&metrics=visitors" \
  | jq '.results.visitors.value')

EVENTS=$(curl -sS -H "Authorization: Bearer $PLAUSIBLE_API_KEY" \
  "${PLAUSIBLE_BASE_URL:-https://plausible.io}/api/v1/stats/aggregate?site_id=$PLAUSIBLE_SITE_ID&period=${window}&metrics=events&filters=event:name==${event}" \
  | jq '.results.events.value')
```

Transform:
```
count    = $EVENTS
sessions = $SESSIONS
rate     = $EVENTS / $SESSIONS   (if sessions == 0, rate = 0)
```

Return:
```jsonc
{"event": "sign_up", "count": 96, "sessions": 18420, "rate": 0.00521}
```

## idioms

- **Plausible is privacy-first.** No per-user or per-session IDs are exposed. Several contract capabilities (`funnel`, `session_quality`) are genuinely not available and are marked `not_implemented` — do not try to fake them.
- **Per-page `conv_rate` is approximated as 0** in `top_pages` / `landing_pages` / `traffic_sources` because computing it per-page from the Stats API requires N+1 requests (one `breakdown` call plus one `aggregate` call per page filtered by the goal). The top-level `conversions()` call gives the site-wide rate, which is enough for `skills/hypothesize.md` to identify "site-wide conversion is low on X page" hypotheses.
- **Bounce rate is 0-100 in the raw response.** The Transform step divides by 100 to match the normalized 0-1 range. If you see bounce rates > 1 in hypotheses, the Transform step was skipped.
- **Windows use Plausible's `period` strings.** Allowed: `12mo`, `6mo`, `month`, `30d`, `7d`, `day`, `realtime`. Map the contract's `window="28d"` to Plausible's `period=30d`.
- **Rate limit**: 600 requests / hour / site on plausible.io. Self-hosted has no enforced limit but be polite.
- **Last verified: 2026-04**

## fallbacks

- **HTTP 5xx / transient failure**: retry once with `period=day`, then log a warning to `run.log` and return `[]` (or `{"event": "<event>", "count": 0, "sessions": 0, "rate": 0}` for the `conversions` capability).
- **HTTP 401 / 403**: stop immediately with `credentials invalid for PLAUSIBLE_API_KEY — check the key has Stats API scope in plausible.io/settings/api-keys`. Do not retry.
- **HTTP 429 (rate limit)**: back off 60 seconds, retry once, then return empty and continue the loop. Log a warning.
- **`mode: fixture`**: bypass every live call and read from `autocro/fixtures/analytics-sample.json`. For every capability, return the pre-shaped slice exactly as the `adapters/analytics/fixture.md` adapter does. This is MANDATORY so `skills/validate-adapter.md` can verify the adapter against the schema without any real credentials.
