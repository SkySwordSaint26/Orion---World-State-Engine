"""The gold annotation contract (`orion_gold_v1.schema.json`, repo root) and a dependency-free validator for it."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "orion_gold_v1.schema.json"


def load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(value, sch, root, path="$"):
    """Supports exactly the keywords this schema uses. Returns a list of error strings."""
    if "$ref" in sch:
        node = root
        for part in sch["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return validate(value, node, root, path)
    errs = []
    types = sch.get("type")
    if types:
        checks = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
                  "string": lambda v: isinstance(v, str), "null": lambda v: v is None,
                  "boolean": lambda v: isinstance(v, bool),
                  "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                  "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}
        if not any(checks[t](value) for t in ([types] if isinstance(types, str) else types)):
            return [f"{path}: expected {types}, got {value!r}"]
    if "const" in sch and value != sch["const"]:
        errs.append(f"{path}: not {sch['const']!r}")
    if "enum" in sch and value not in sch["enum"]:
        errs.append(f"{path}: {value!r} not in enum")
    if isinstance(value, str):
        if "minLength" in sch and len(value) < sch["minLength"]:
            errs.append(f"{path}: too short")
        if "pattern" in sch and not re.search(sch["pattern"], value):
            errs.append(f"{path}: {value!r} !~ {sch['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in sch and value < sch["minimum"]:
        errs.append(f"{path}: below minimum")
    if isinstance(value, dict):
        for req in sch.get("required", []):
            if req not in value:
                errs.append(f"{path}: missing {req}")
        props = sch.get("properties", {})
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], root, f"{path}.{k}")
            elif sch.get("additionalProperties") is False:
                errs.append(f"{path}: unexpected {k}")
    if isinstance(value, list):
        if "minItems" in sch and len(value) < sch["minItems"]:
            errs.append(f"{path}: too few items")
        if sch.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value):
            errs.append(f"{path}: items not unique")
        for i, v in enumerate(value):
            errs += validate(v, sch.get("items", {}), root, f"{path}[{i}]")
    return errs


def schema_errors(doc: Any) -> List[str]:
    """Every violation of the gold schema in `doc` (empty list = valid)."""
    s = load_schema()
    return validate(doc, s, s)
