# Adapter: Google Analytics 4

kind: analytics
id: ga4

Reference adapter for the [Google Analytics 4 Data API](https://developers.google.com/analytics/devguides/reporting/data/v1). GA4 is the most common analytics tool on the web — this adapter exists so "I use GA4" users can go from drop-in to running the inner loop in under 10 minutes without authoring a markdown playbook.

Authentication uses a Google Cloud **service account JSON keyfile**, exchanged for a short-lived OAuth2 token via a signed JWT. All signing is done with `openssl` (which ships by default on macOS/Linux); no Python RSA libraries or `google-auth` package are required — this keeps the adapter stdlib-only consistent with the rest of `harness/`.

## requires

```yaml
env:
  - GOOGLE_APPLICATION_CREDENTIALS    # absolute path to the service-account JSON keyfile
  - GA4_PROPERTY_ID                   # numeric GA4 property id (NOT the "measurement id" G-XXXXXX)
command: [curl, jq, openssl, python3, base64]
```

Create the service account at <https://console.cloud.google.com/iam-admin/serviceaccounts>, grant it the "Viewer" role on your GA4 property at <https://analytics.google.com/analytics/web/#/aXXXXXXXXX/admin/properties/propertyId/propertyaccessmanagement>, and download the JSON keyfile. Export:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/keyfile.json
export GA4_PROPERTY_ID=123456789
```

## health

1. Confirm the keyfile exists and is valid JSON with `client_email` and `private_key` fields:
   ```bash
   jq -e '.client_email and .private_key' "$GOOGLE_APPLICATION_CREDENTIALS" > /dev/null
   ```
   → expect exit 0.
2. Mint an access token via the JWT flow documented in `## read` below. Expect the response to contain a non-empty `access_token`.
3. Issue a 1-row test report:
   ```bash
   curl -sS -X POST \
     -H "Authorization: Bearer $ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     "https://analyticsdata.googleapis.com/v1beta/properties/$GA4_PROPERTY_ID:runReport" \
     -d '{"dateRanges":[{"startDate":"7daysAgo","endDate":"today"}],"metrics":[{"name":"sessions"}],"limit":1}'
   ```
   → expect HTTP 200 and a `rows` array (may be empty on brand-new properties, which is acceptable).
4. If the token exchange returns `invalid_grant`: the service account does not have access to the property. Stop with `GA4 service account lacks Viewer role on property $GA4_PROPERTY_ID — add it in the GA4 admin UI under Property Access Management`.
5. If HTTP 403 on runReport: the GA4 Data API is not enabled for this GCP project. Stop with `GA4 Data API disabled — enable at https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com`.

## capabilities

- top_pages: implemented
- landing_pages: implemented
- funnel: not_implemented (GA4 Data API v1beta does not expose funnel queries; they require the Data API Advanced subscription or direct BigQuery access)
- traffic_sources: implemented
- conversions: implemented
- session_quality: implemented

## read

All capabilities share the JWT / access token flow. Define this helper at the top of the adapter session:

```bash
# Mint a short-lived access token from the service-account keyfile.
# Writes the token to $ACCESS_TOKEN. Safe to call once per iteration;
# the token is valid for 1 hour. Re-call only when it expires.

ga4_mint_token() {
  local SA_JSON NOW EXP HEADER_B64 PAYLOAD PAYLOAD_B64 SIGNING_INPUT SIGNATURE JWT RESP
  SA_JSON="$GOOGLE_APPLICATION_CREDENTIALS"

  NOW=$(date -u +%s)
  EXP=$((NOW + 3600))

  HEADER_B64=$(printf '{"alg":"RS256","typ":"JWT"}' \
                | base64 | tr -d '\n' | tr '/+' '_-' | tr -d '=')

  PAYLOAD=$(jq -nc \
    --arg iss   "$(jq -r '.client_email' "$SA_JSON")" \
    --arg aud   "https://oauth2.googleapis.com/token" \
    --arg scope "https://www.googleapis.com/auth/analytics.readonly" \
    --argjson iat "$NOW" --argjson exp "$EXP" \
    '{iss:$iss, scope:$scope, aud:$aud, iat:$iat, exp:$exp}')
  PAYLOAD_B64=$(printf '%s' "$PAYLOAD" | base64 | tr -d '\n' | tr '/+' '_-' | tr -d '=')

  SIGNING_INPUT="${HEADER_B64}.${PAYLOAD_B64}"
  SIGNATURE=$(printf '%s' "$SIGNING_INPUT" \
    | openssl dgst -sha256 -sign <(jq -r '.private_key' "$SA_JSON") -binary \
    | base64 | tr -d '\n' | tr '/+' '_-' | tr -d '=')

  JWT="${SIGNING_INPUT}.${SIGNATURE}"

  RESP=$(curl -sS -X POST "https://oauth2.googleapis.com/token" \
    -d "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer" \
    --data-urlencode "assertion=${JWT}")

  ACCESS_TOKEN=$(printf '%s' "$RESP" | jq -r '.access_token')
  if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" = "null" ]; then
    printf 'GA4 TOKEN EXCHANGE FAILED: %s\n' "$RESP" >&2
    return 1
  fi
}
```

Then the helper that calls `runReport`:

```bash
ga4_run_report() {
  local body="$1"
  curl -sS -X POST \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    "https://analyticsdata.googleapis.com/v1beta/properties/$GA4_PROPERTY_ID:runReport" \
    -d "$body"
}
```

### top_pages(window="7d", limit=25)

```bash
ga4_mint_token
ga4_run_report '{
  "dateRanges":  [{"startDate":"7daysAgo","endDate":"today"}],
  "dimensions":  [{"name":"pagePath"}],
  "metrics":     [
    {"name":"sessions"},
    {"name":"bounceRate"},
    {"name":"conversions"},
    {"name":"averageSessionDuration"}
  ],
  "orderBys":    [{"metric":{"metricName":"sessions"},"desc":true}],
  "limit": 25
}'
```

Transform:
```
for each row in .rows:
  path        = row.dimensionValues[0].value
  sessions    = int(row.metricValues[0].value)
  bounce_rate = float(row.metricValues[1].value)        (GA4 already returns fraction 0-1)
  conv_rate   = float(row.metricValues[2].value) / max(1, sessions)
  avg_time_s  = float(row.metricValues[3].value)
```

Return:
```jsonc
[{"path": "/pricing", "sessions": 12340, "bounce_rate": 0.61, "conv_rate": 0.018, "avg_time_s": 42}, ...]
```

### landing_pages(window="7d", limit=25)

```bash
ga4_run_report '{
  "dateRanges":  [{"startDate":"7daysAgo","endDate":"today"}],
  "dimensions":  [{"name":"landingPage"}],
  "metrics":     [
    {"name":"sessions"},
    {"name":"bounceRate"},
    {"name":"conversions"}
  ],
  "orderBys":    [{"metric":{"metricName":"sessions"},"desc":true}],
  "limit": 25
}'
```

Transform: same shape, map `landingPage` → `path`, `sessions` → `landings`, derive `conv_rate`.

Return:
```jsonc
[{"path": "/pricing", "landings": 8420, "bounce_rate": 0.68, "conv_rate": 0.012}, ...]
```

### traffic_sources(window="7d", limit=25)

```bash
ga4_run_report '{
  "dateRanges":  [{"startDate":"7daysAgo","endDate":"today"}],
  "dimensions":  [{"name":"sessionSource"}, {"name":"sessionMedium"}],
  "metrics":     [{"name":"sessions"}, {"name":"conversions"}],
  "orderBys":    [{"metric":{"metricName":"sessions"},"desc":true}],
  "limit": 25
}'
```

Transform: map `sessionSource` → `source`, `sessionMedium` → `medium`, derive `conv_rate = conversions / sessions`.

Return:
```jsonc
[{"source": "google", "medium": "organic", "sessions": 5200, "conv_rate": 0.021}, ...]
```

### conversions(event, window="7d")

```bash
ga4_run_report "$(jq -nc --arg ev "$event" '{
  dateRanges:  [{startDate:"7daysAgo", endDate:"today"}],
  metrics:     [
    {name: "sessions"},
    {name: "eventCount"}
  ],
  dimensionFilter: {
    filter: {fieldName: "eventName", stringFilter: {matchType: "EXACT", value: $ev}}
  }
}')"
```

Transform: the totals come from `.totals[0]` not `.rows`. `count = eventCount`, `sessions = sessions`, `rate = count / sessions` (guard divide-by-zero with 0).

Return:
```jsonc
{"event": "sign_up", "count": 410, "sessions": 12340, "rate": 0.0332}
```

### session_quality(path, window="7d")

```bash
ga4_run_report "$(jq -nc --arg p "$path" '{
  dateRanges:  [{startDate:"7daysAgo", endDate:"today"}],
  dimensions:  [{name:"pagePath"}],
  metrics:     [
    {name:"averageSessionDuration"},
    {name:"bounceRate"},
    {name:"engagementRate"}
  ],
  dimensionFilter: {filter: {fieldName:"pagePath", stringFilter:{matchType:"EXACT", value:$p}}}
}')"
```

Transform:
```
path             = path (echo back; GA4 filter guarantees it matched)
avg_time_s       = float(row.metricValues[0].value)
scroll_depth_p50 = 0   (GA4 Data API does not expose scroll percentile; leave 0 and note in ## idioms.
                        hypothesize.md tolerates 0 but will downweight this citation)
bounce_rate      = float(row.metricValues[1].value)
engagement_score = float(row.metricValues[2].value)
```

Return:
```jsonc
{"path": "/pricing", "avg_time_s": 42, "scroll_depth_p50": 0.0, "bounce_rate": 0.61, "engagement_score": 0.33}
```

## idioms

- **GA4 property id is numeric, not the measurement id.** Users frequently confuse `GA4_PROPERTY_ID` (e.g. `123456789`) with the "G-XXXXXXX" measurement id visible on the tag. The property id is at analytics.google.com → Admin → Property Settings → Property ID.
- **Service account needs Viewer role on the property.** The IAM role on the GCP project isn't enough — GA4 has its own access control at `Property access management`.
- **GA4 Data API is rate-limited to 25,000 tokens/day per property** on the free tier. Each query costs ~1 token. 25k is plenty for overnight runs, but do not run dozens of parallel inner loops on the same property.
- **Timezone.** GA4 reports are in the property's configured timezone, NOT UTC. If the property is set to America/New_York, `7daysAgo` means "7 days ago in ET". Document this in hypothesis.md if you're citing date-sensitive data.
- **`bounceRate` in GA4 v4 is 1 - `engagementRate`.** GA4 changed the meaning of bounce rate between UA and GA4. The adapter uses GA4's native `bounceRate` metric, which is already a fraction 0-1 (no division by 100 needed).
- **No scroll depth from the Data API.** `scroll_depth_p50` in `session_quality` is always 0 unless you've set up scroll depth events as a custom dimension. The reference adapter doesn't try to parse custom dimensions.
- **No funnels.** GA4 funnel exploration is a UI-only feature on the free tier; the Data API exposes it only under the paid Analytics 360 tier. `funnel` is marked `not_implemented` — users who need it should use the BigQuery export instead.
- **Last verified: 2026-04**

## fallbacks

- **`invalid_grant` token error**: the service account was removed from the property access list. Stop with a clear message and the fix link.
- **HTTP 403 on runReport**: Data API not enabled. Stop with the enable-API link.
- **HTTP 429 (quota exhausted)**: back off 5 minutes, retry once, return empty on second failure.
- **HTTP 5xx / token exchange 5xx**: retry once with a narrower window (`3daysAgo`), return empty on second failure.
- **Token expired mid-run**: re-call `ga4_mint_token` and retry the failed request once.
- **`mode: fixture`**: bypass every live call, skip the JWT flow entirely (no need for real credentials), and read from `autocro/fixtures/analytics-sample.json`. For each capability, return the pre-shaped slice exactly as `adapters/analytics/fixture.md` does. This is MANDATORY for `skills/validate-adapter.md`, and it is the only path that makes this adapter testable without a real GCP service account.
