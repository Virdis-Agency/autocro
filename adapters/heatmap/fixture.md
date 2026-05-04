# Adapter: Fixture Heatmap

kind: heatmap
id: fixture

Reads canned heatmap data from `fixtures/heatmap-sample.json`. Used for offline verification and end-to-end smoke tests.

## requires

```yaml
env: []
command: [cat]
```

## health

1. Confirm `autocro/fixtures/heatmap-sample.json` exists and parses as JSON.
2. Confirm it has keys for at least `page_attention`, `click_map`, `rage_clicks`.

## capabilities

- page_attention: implemented
- click_map: implemented
- rage_clicks: implemented
- session_sample: implemented

## read

### page_attention(path)

```
data = read_json("autocro/fixtures/heatmap-sample.json")
for entry in data["page_attention"]:
    if entry["path"] == path:
        return entry
return {"path": path, "scroll_depth_p50": 0.0, "scroll_depth_p90": 0.0, "hotspots": []}
```

### click_map(path, limit)

```
data = read_json("autocro/fixtures/heatmap-sample.json")
return data["click_map"].get(path, [])[:limit]
```

### rage_clicks(path, limit)

```
data = read_json("autocro/fixtures/heatmap-sample.json")
return data["rage_clicks"].get(path, [])[:limit]
```

### session_sample(path, n)

```
data = read_json("autocro/fixtures/heatmap-sample.json")
return data.get("session_sample", {}).get(path, [])[:n]
```

## idioms

- `hypothesis_source` should be tagged `fixture:<capability>`.
- Fixture heatmap data is designed to expose specific weaknesses in the demo site for the smoke test — rage clicks on the disabled submit button, low scroll depth on pricing, attention clustered on irrelevant nav.

## fallbacks

- **File missing**: health fails.
- **Malformed JSON**: stop with a clear parse error.
