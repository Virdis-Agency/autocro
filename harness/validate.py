#!/usr/bin/env python3
"""
autocro schema validator — stdlib only.

Invoked by markdown skills (skills/setup-check.md, skills/validate-adapter.md)
to check config.yaml and adapter capability responses against the JSON schemas
under harness/schemas/. Deliberately minimal: handles only the draft-07 subset
actually used by those schemas (type, required, properties, items, enum,
pattern, minLength, minimum, maximum, additionalProperties, oneOf, $ref to
local $defs, minItems).

Usage
-----
    python3 harness/validate.py <kind> <capability> --stdin
    python3 harness/validate.py <kind> <capability> --response-file path.json
    python3 harness/validate.py config --stdin

Exit codes
----------
    0  validation passed
    2  validation failed (user error — wrong shape, missing key, etc.)
    3  schema or input could not be loaded (user error — file missing / bad JSON)
    4  internal crash (bug in this helper — never blame the user)

On exit 2, a structured, line-addressed error block is written to stderr.
The calling skill surfaces it verbatim so the human sees: WHAT failed, WHERE,
WHAT was expected, and HOW to fix it.
"""

import argparse
import json
import re
import sys
import traceback
from pathlib import Path

HARNESS_DIR = Path(__file__).resolve().parent
SCHEMAS_DIR = HARNESS_DIR / "schemas"

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ValidationError(Exception):
    def __init__(self, at, problem, expected=None, hint=None):
        self.at = at
        self.problem = problem
        self.expected = expected
        self.hint = hint
        super().__init__(problem)


def emit_error(header, at, problem, expected, hint, schema_path, extra=None):
    """Write a structured error block to stderr."""
    lines = [header, f"at: {at}", f"problem: {problem}"]
    if expected:
        lines.append(f"expected: {expected}")
    if extra:
        lines.append(extra)
    lines.append(f"schema: {schema_path}")
    if hint:
        lines.append(f"fix: {hint}")
    sys.stderr.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Schema walker
# ---------------------------------------------------------------------------


def type_of(data):
    """Return the JSON Schema type name for a Python value."""
    if data is None:
        return "null"
    if isinstance(data, bool):
        return "boolean"
    if isinstance(data, int):
        return "integer"
    if isinstance(data, float):
        return "number"
    if isinstance(data, str):
        return "string"
    if isinstance(data, list):
        return "array"
    if isinstance(data, dict):
        return "object"
    return "unknown"


def type_matches(data, expected_type):
    actual = type_of(data)
    if actual == expected_type:
        return True
    # integer is also a number
    if expected_type == "number" and actual == "integer":
        return True
    return False


def resolve_ref(ref, root):
    if not ref.startswith("#/"):
        raise ValidationError("<schema>", f"unsupported $ref {ref!r}",
                              expected="#/$defs/... style local reference")
    node = root
    for part in ref.lstrip("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            raise ValidationError("<schema>", f"$ref target not found: {ref}")
        node = node[part]
    return node


def walk(data, schema, path, root):
    """Validate `data` against `schema`. Raises ValidationError on mismatch."""
    if "$ref" in schema:
        return walk(data, resolve_ref(schema["$ref"], root), path, root)

    if "oneOf" in schema:
        errors = []
        for sub in schema["oneOf"]:
            try:
                walk(data, sub, path, root)
                return  # any-match is fine for nullable-field use case
            except ValidationError as e:
                errors.append(f"  - {e.problem}")
        raise ValidationError(
            path,
            "value does not match any allowed shape",
            expected="one of:\n" + "\n".join(errors),
            hint=f"the value at {path} must match exactly one of the allowed shapes",
        )

    expected_type = schema.get("type")
    if expected_type is not None and not type_matches(data, expected_type):
        raise ValidationError(
            path,
            f"expected type {expected_type}, got {type_of(data)}",
            expected=expected_type,
            hint=f"convert the value at {path} to {expected_type}",
        )

    if "enum" in schema and data not in schema["enum"]:
        allowed = " | ".join(repr(v) for v in schema["enum"])
        raise ValidationError(
            path,
            f"value {data!r} not in allowed set",
            expected=allowed,
            hint=f"use one of the allowed values at {path}",
        )

    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            raise ValidationError(
                path,
                f"string too short (length {len(data)} < {schema['minLength']})",
                hint=f"provide a non-empty string at {path}",
            )
        if "pattern" in schema and not re.search(schema["pattern"], data):
            raise ValidationError(
                path,
                f"string {data!r} does not match required pattern",
                expected=schema["pattern"],
                hint=f"format the value at {path} to match the pattern",
            )

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            raise ValidationError(
                path,
                f"value {data} is below minimum {schema['minimum']}",
                hint=f"the value at {path} must be >= {schema['minimum']}",
            )
        if "maximum" in schema and data > schema["maximum"]:
            raise ValidationError(
                path,
                f"value {data} is above maximum {schema['maximum']}",
                hint=f"the value at {path} must be <= {schema['maximum']}",
            )

    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            raise ValidationError(
                path,
                f"array has {len(data)} items, minimum {schema['minItems']}",
                hint=f"the array at {path} must have at least {schema['minItems']} item(s)",
            )
        items_schema = schema.get("items")
        if items_schema is not None:
            for i, item in enumerate(data):
                walk(item, items_schema, f"{path}[{i}]", root)

    if isinstance(data, dict):
        for required_key in schema.get("required", []):
            if required_key not in data:
                found = ", ".join(sorted(data.keys())) if data else "(empty)"
                raise ValidationError(
                    path,
                    f"required key {required_key!r} is missing (found keys: {found})",
                    expected=f"key {required_key!r}",
                    hint=(
                        f"add {required_key!r} to the object at {path}. if your tool returns "
                        f"this value under a different name, add a Transform step in the "
                        f"adapter's ## read section to rename the key."
                    ),
                )
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in data.items():
            child_path = f"{path}.{key}" if not path.endswith("$") else f"$.{key}"
            if key in properties:
                walk(value, properties[key], child_path, root)
            elif additional is False:
                allowed = ", ".join(sorted(properties.keys())) or "(none)"
                raise ValidationError(
                    child_path,
                    f"unexpected key {key!r} (not allowed by schema)",
                    expected=f"one of: {allowed}",
                    hint=(
                        f"remove {key!r} from the object at {path}, OR if the adapter is "
                        f"returning it under the wrong name, rename it to one of: {allowed}. "
                        f"this usually means the adapter's ## read section needs a Transform "
                        f"step to align the raw tool response with the normalized contract."
                    ),
                )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_schema(kind):
    schema_path = SCHEMAS_DIR / f"{kind}.json"
    if not schema_path.exists():
        sys.stderr.write(
            f"SCHEMA LOAD FAILED: {schema_path} does not exist\n"
            f"known kinds: analytics, heatmap, abtest, config\n"
            f"fix: ensure harness/schemas/{kind}.json is checked in.\n"
        )
        sys.exit(3)
    try:
        return json.loads(schema_path.read_text()), schema_path
    except json.JSONDecodeError as exc:
        sys.stderr.write(
            f"SCHEMA LOAD FAILED: {schema_path} is not valid JSON\n"
            f"details: {exc}\n"
            f"fix: repair the JSON syntax in the schema file.\n"
        )
        sys.exit(3)


def select_subschema(root, capability):
    defs = root.get("$defs", {})
    if capability not in defs or capability.startswith("_"):
        public = sorted(k for k in defs if not k.startswith("_"))
        sys.stderr.write(
            f"SCHEMA LOAD FAILED: capability {capability!r} is not defined in this schema\n"
            f"available capabilities: {', '.join(public) or '(none)'}\n"
            f"fix: check the spelling, or mark the capability not_implemented in the adapter.\n"
        )
        sys.exit(3)
    return defs[capability]


def load_input(args):
    if args.response_file:
        path = Path(args.response_file)
        if not path.exists():
            sys.stderr.write(
                f"INPUT LOAD FAILED: {path} does not exist\n"
                f"fix: write the adapter response to this path before invoking validate.py.\n"
            )
            sys.exit(3)
        raw = path.read_text()
    else:
        raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        source = args.response_file or "stdin"
        sys.stderr.write(
            f"INPUT LOAD FAILED: {source} is not valid JSON\n"
            f"details: {exc}\n"
            f"fix: ensure the adapter returns well-formed JSON for this capability.\n"
        )
        sys.exit(3)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_capability(args):
    """Validate one adapter capability response against its schema."""
    schema, schema_path = load_schema(args.kind)
    subschema = select_subschema(schema, args.capability)
    data = load_input(args)
    try:
        walk(data, subschema, "$", schema)
    except ValidationError as exc:
        header = f"VALIDATION FAILED: {args.kind}::{args.capability}"
        emit_error(header, exc.at, exc.problem, exc.expected, exc.hint, schema_path)
        sys.exit(2)
    sys.stderr.write(f"VALIDATION OK: {args.kind}::{args.capability}\n")
    sys.exit(0)


def scan_literal_secrets(adapters, problems):
    """Heuristic: flag suspicious raw credentials in config.adapters.*.

    Rule: inside any adapter config block, flag string values 32+ chars of
    base64-ish characters ([A-Za-z0-9/_+=-]) unless the key name ends in
    _env, _id, or _url (those are metadata, not credentials).
    """
    pattern = re.compile(r"^[A-Za-z0-9/_+=\-]{32,}$")
    safe_suffixes = ("_env", "_id", "_url")
    for adapter_id, block in adapters.items():
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if not isinstance(value, str):
                continue
            if any(key.endswith(s) for s in safe_suffixes):
                continue
            if pattern.match(value):
                problems.append((
                    f"$.adapters.{adapter_id}.{key}",
                    f"value at $.adapters.{adapter_id}.{key} looks like a literal secret",
                    None,
                    (
                        f"move the value into an environment variable and reference it "
                        f"via a sibling key '{key}_env: \"NAME_OF_VAR\"'. literal credentials "
                        f"must never appear in config.yaml — the file is gitignored but "
                        f"still ends up in backups, crash reports, and diffs."
                    ),
                ))


def cmd_config(args):
    schema, schema_path = load_schema("config")
    data = load_input(args)

    try:
        walk(data, schema, "$", schema)
    except ValidationError as exc:
        emit_error("CONFIG INVALID: config.yaml", exc.at, exc.problem,
                   exc.expected, exc.hint, schema_path)
        sys.exit(2)

    # Post-schema rules that draft-07 cannot express.
    problems = []

    weights = data.get("prevalidation", {}).get("weights", {}) or {}
    total = sum(float(weights.get(k, 0) or 0)
                for k in ("lighthouse", "llm_judge", "persona", "heuristic"))
    if abs(total - 1.0) > 0.001:
        current = " ".join(f"{k}={weights.get(k)}"
                           for k in ("lighthouse", "llm_judge", "persona", "heuristic"))
        problems.append((
            "$.prevalidation.weights",
            f"weights sum to {total:.3f}, expected ~1.0 (±0.001)",
            f"current: {current}",
            "re-balance the four values so they sum to 1.0. Example: 0.15 / 0.40 / 0.30 / 0.15.",
        ))

    thresholds = data.get("prevalidation", {}).get("thresholds", {}) or {}
    discard = thresholds.get("discard")
    push = thresholds.get("push")
    if discard is not None and push is not None and discard >= push:
        problems.append((
            "$.prevalidation.thresholds",
            f"discard ({discard}) must be strictly less than push ({push})",
            None,
            "set discard < push so variants have a meaningful decision boundary between the two.",
        ))

    adapters = data.get("adapters", {}) or {}
    scan_literal_secrets(adapters, problems)

    if problems:
        sys.stderr.write("CONFIG INVALID: config.yaml\n")
        for at, problem, current, hint in problems:
            sys.stderr.write(f"at: {at}\n")
            sys.stderr.write(f"problem: {problem}\n")
            if current:
                sys.stderr.write(f"{current}\n")
            sys.stderr.write(f"schema: {schema_path}\n")
            if hint:
                sys.stderr.write(f"fix: {hint}\n")
            sys.stderr.write("\n")
        sys.exit(2)

    sys.stderr.write("CONFIG OK\n")
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="autocro schema validator (stdlib only)",
    )
    parser.add_argument("kind", help="one of: analytics, heatmap, abtest, config")
    parser.add_argument("capability", nargs="?",
                        help="capability name (required unless kind=config)")
    parser.add_argument("--stdin", action="store_true",
                        help="read input JSON from stdin")
    parser.add_argument("--response-file",
                        help="read input JSON from this file instead of stdin")
    args = parser.parse_args()

    if not args.stdin and not args.response_file:
        parser.error("provide either --stdin or --response-file")

    if args.kind == "config":
        cmd_config(args)
        return

    if args.kind not in ("analytics", "heatmap", "abtest"):
        parser.error(f"unknown kind: {args.kind!r} (expected analytics | heatmap | abtest | config)")
    if args.capability is None:
        parser.error("capability is required unless kind=config")

    cmd_capability(args)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.stderr.write(
            "SETUP CHECK HELPER CRASHED — internal validator error.\n"
            "This is a bug in harness/validate.py, not a user-fixable problem.\n"
            "Calling skills should treat exit 4 as 'degraded mode' and continue with a warning.\n"
            "Traceback:\n"
        )
        traceback.print_exc(file=sys.stderr)
        sys.exit(4)
