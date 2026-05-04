# Adapter: Fixture Analytics

kind: analytics
id: fixture

Reads canned analytics data from `fixtures/analytics-sample.json`. Used for offline verification, evaluation of the framework before accounts are set up, and end-to-end smoke tests.

## requires

```yaml
env: []
command: [cat]   # or any file-reading mechanism; agent can use Read tool directly
```

## health

1. Confirm `autocro/fixtures/analytics-sample.json` exists and parses as JSON.
2. Confirm the fixture file has keys for at least `top_pages`, `landing_pages`, `funnel`, `traffic_sources`, `conversions`.

## capabilities

- top_pages: implemented
- landing_pages: implemented
- funnel: implemented
- traffic_sources: implemented
- conversions: implemented
- session_quality: implemented

## read

For every capability, read `autocro/fixtures/analytics-sample.json` and return the corresponding key. The fixture file is already pre-shaped to match the normalized contract — no transformation needed.

### top_pages(window, limit)

```
data = read_json("autocro/fixtures/analytics-sample.json")
return data["top_pages"][:limit]
```

The `window` parameter is logged but ignored (fixtures are a single snapshot).

### landing_pages(window, limit)

```
return read_json("autocro/fixtures/analytics-sample.json")["landing_pages"][:limit]
```

### funnel(steps)

```
return read_json("autocro/fixtures/analytics-sample.json")["funnel"]
```

### traffic_sources(window, limit)

```
return read_json("autocro/fixtures/analytics-sample.json")["traffic_sources"][:limit]
```

### conversions(event, window)

```
data = read_json("autocro/fixtures/analytics-sample.json")
return data["conversions"]
```

### session_quality(path, window)

```
data = read_json("autocro/fixtures/analytics-sample.json")
for entry in data.get("session_quality", []):
    if entry["path"] == path:
        return entry
return {"path": path, "avg_time_s": 0, "scroll_depth_p50": 0.0,
        "bounce_rate": 0.0, "engagement_score": 0.0}
```

## idioms

- Fixture data represents a deliberately weak demo site — expect low conversion rates and obvious drop-offs to give `skills/hypothesize.md` plenty to work with.
- `hypothesis_source` should be tagged `fixture:<capability>` so the analysis notebook clearly separates fixture-mode runs from live runs.

## fallbacks

- **File missing**: setup fails health check; program.md stops. Re-run Phase 1 verification to regenerate the fixture.
- **Malformed JSON**: stop with a clear parse error.
- `mode: fixture` is this adapter's only mode.
