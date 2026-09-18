"""JSON Schema -> Gemini `Schema`.

pydantic emits standard JSON Schema; the Gemini API accepts a deliberately
smaller dialect and rejects the rest outright. The differences are not
cosmetic and are worth naming, because each one produced a real 400:

* **Types are upper-case enums.** ``"string"`` is rejected; ``"STRING"`` is not.
* **`additionalProperties` is forbidden**, so ``ConfigDict(extra="forbid")`` --
  which we want everywhere else -- has to be stripped here.
* **`$ref` / `$defs` are not resolved**, so nested models must be inlined.
* **`anyOf: [T, null]`**, which is how pydantic spells ``T | None``, has to
  become ``T`` plus ``nullable: true``.
* **Validation keywords** (`minimum`, `maxLength`, `pattern`, `default`,
  `title`, `examples`) are ignored at best and rejected at worst.

Doing this conversion in one audited place is much safer than hand-writing
parallel schemas for the six tools and four output models, which would drift
from the pydantic models they are supposed to mirror -- and drift here means the
model is told about a field that no longer exists.
"""

from __future__ import annotations

from typing import Any

_TYPE_MAP = {
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
    "null": "STRING",
}

#: Everything Gemini's Schema actually understands.
_KEEP = {"type", "description", "properties", "required", "items", "enum", "nullable"}


def _resolve(node: Any, defs: dict[str, Any], depth: int = 0) -> Any:
    """Inline a $ref, guarding against a cycle.

    A self-referential model would otherwise recurse forever. Depth-limiting
    rather than cycle-detecting is crude, but no schema here is more than three
    deep and a wrong answer at depth 12 is better than a hung process.
    """
    if depth > 12 or not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if ref and ref.startswith("#/$defs/"):
        target = defs.get(ref.split("/")[-1], {})
        merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
        return _resolve(merged, defs, depth + 1)
    return node


def to_gemini_schema(
    schema: dict[str, Any], defs: dict[str, Any] | None = None, depth: int = 0
) -> dict[str, Any]:
    """Convert one JSON Schema node into Gemini's dialect."""
    if defs is None:
        defs = schema.get("$defs", {}) or {}
    resolved = _resolve(schema, defs, depth)
    if not isinstance(resolved, dict):
        return {"type": "STRING"}
    schema = resolved

    nullable = False
    variants = schema.get("anyOf") or schema.get("oneOf")
    if variants:
        concrete = [v for v in variants if _resolve(v, defs, depth).get("type") != "null"]
        nullable = len(concrete) != len(variants)
        if not concrete:
            return {"type": "STRING", "nullable": True}
        # Gemini has no union type. The first concrete variant is the honest
        # choice: every union in this codebase is `T | None`, so there is only
        # ever one.
        merged = to_gemini_schema(concrete[0], defs, depth + 1)
        if nullable:
            merged["nullable"] = True
        if "description" in schema:
            merged.setdefault("description", schema["description"])
        return merged

    out: dict[str, Any] = {}
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        nullable = "null" in raw_type
        raw_type = next((t for t in raw_type if t != "null"), "string")
    out["type"] = _TYPE_MAP.get(str(raw_type or "string"), "STRING")

    for key in ("description", "enum"):
        if key in schema:
            out[key] = schema[key]
    if nullable:
        out["nullable"] = True

    if out["type"] == "OBJECT":
        props = schema.get("properties") or {}
        if props:
            out["properties"] = {k: to_gemini_schema(v, defs, depth + 1) for k, v in props.items()}
        required = [r for r in schema.get("required", []) if r in props]
        if required:
            out["required"] = required
        if not props:
            # Gemini rejects an OBJECT with no properties. A free-form dict is
            # not expressible, so declare it as a string and let the tool's own
            # pydantic model do the real validation on the way in.
            out = {
                "type": "STRING",
                **({"description": out["description"]} if "description" in out else {}),
            }

    if out["type"] == "ARRAY":
        out["items"] = to_gemini_schema(schema.get("items") or {"type": "string"}, defs, depth + 1)

    return {k: v for k, v in out.items() if k in _KEEP}


def tool_parameters(model_schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a pydantic model's schema into a function-declaration parameter block."""
    converted = to_gemini_schema(model_schema)
    if converted.get("type") != "OBJECT":
        return {"type": "OBJECT", "properties": {}}
    return converted
