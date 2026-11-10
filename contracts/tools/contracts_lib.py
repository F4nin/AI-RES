"""Contract validation helpers (S01, ADR-004/009). Stdlib + pinned deps only; no network access."""
import copy
import hashlib
import json
from pathlib import Path

import yaml
from jsonschema import Draft7Validator, Draft202012Validator
from openapi_spec_validator import validate as _validate_openapi
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS = Path(__file__).resolve().parent.parent
REPO = CONTRACTS.parent
# JSON data files in json-schema/ that are not JSON Schemas (explicit allowlist; anything else must declare $schema).
NON_SCHEMA_DATA = {"AI_RES_Operation_and_Readiness_Gate_State_Machine_v1.2.json"}
ASYNCAPI_SPEC = CONTRACTS / "node_modules/@asyncapi/specs/schemas/3.1.0.json"


def load(path):
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text) if str(path).endswith(".json") else yaml.safe_load(text)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------- mirror (ADR-009) ----------
def verify_mirror(contracts=CONTRACTS, repo=REPO):
    """Published files must equal docs/architecture sources and the SHA-256 in the baseline manifest."""
    errors = []
    mapping = load(contracts / "mirror-map.json")
    if not mapping.get("files"):
        return ["mirror-map.json: no files mapped"]
    manifest = {f["path"]: f["sha256"] for f in load(repo / mapping["manifest"])["files"]}
    for entry in mapping["files"]:
        pub, src = contracts / entry["published"], repo / mapping["sourceDir"] / entry["source"]
        want = manifest.get(entry["source"])
        if want is None:
            errors.append(f"{entry['source']}: not listed in baseline manifest")
        if not pub.exists():
            errors.append(f"{entry['published']}: missing")
            continue
        got = sha256(pub)
        if want is not None and got != want:
            errors.append(f"{entry['published']}: sha256 {got[:12]} != manifest {want[:12]}")
        if not src.exists():
            errors.append(f"{entry['source']}: canonical source missing in {mapping['sourceDir']} (discrepancy report required)")
        elif pub.read_bytes() != src.read_bytes():
            errors.append(f"{entry['published']}: differs from {mapping['sourceDir']}/{entry['source']}")
    return errors


# ---------- $ref checking ----------
def _pointer(doc, frag):
    node = doc
    for part in [p for p in frag.lstrip("#").split("/") if p]:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise KeyError(frag)
    return node


def iter_refs(node, trail=""):
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            yield trail, node["$ref"]
        for k, v in node.items():
            yield from iter_refs(v, f"{trail}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_refs(v, f"{trail}/{i}")


def check_refs(path):
    """Every local and relative-file $ref must resolve. URL refs ($id based) are checked by validate_jsonschema."""
    path = Path(path)
    doc = load(path)
    errors = []
    for where, ref in iter_refs(doc):
        if "://" in ref:
            continue
        file_part, _, frag = ref.partition("#")
        try:
            target = doc if not file_part else load(path.parent / file_part)
            _pointer(target, frag)
        except Exception:
            errors.append(f"{path.name}:{where}: unresolved $ref {ref}")
    return errors


# ---------- validators ----------
def validate_openapi(path):
    doc = load(path)
    try:
        _validate_openapi(doc)
    except Exception as exc:
        return [f"{Path(path).name}: {type(exc).__name__}: {str(exc).splitlines()[0]}"]
    return check_refs(path)


def validate_asyncapi_doc(doc, name):
    schema = json.loads(ASYNCAPI_SPEC.read_text())
    return [f"{name}: {'/'.join(map(str, e.absolute_path))}: {e.message[:160]}"
            for e in Draft7Validator(schema).iter_errors(doc)]


def validate_asyncapi(path):
    return validate_asyncapi_doc(load(path), Path(path).name) + check_refs(path)


def schema_registry(root=CONTRACTS / "json-schema"):
    reg, seen = Registry(), {}
    for f in sorted(root.rglob("*.json")):
        s = load(f)
        if isinstance(s, dict) and "$id" in s:
            if s["$id"] in seen:
                raise ValueError(f"duplicate $id {s['$id']} in {f.name} and {seen[s['$id']]}")
            seen[s["$id"]] = f.name
            reg = reg.with_resource(s["$id"], Resource.from_contents(s, default_specification=DRAFT202012))
    return reg


def validate_jsonschema(path, registry=None):
    """Meta-validate against Draft 2020-12 and resolve every $ref (local, relative, or $id-based)."""
    path = Path(path)
    schema = load(path)
    if path.name in NON_SCHEMA_DATA:
        return []
    if not isinstance(schema, dict) or "$schema" not in schema:
        return [f"{path.name}: missing $schema (not allowlisted as non-schema data)"]
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return [f"{path.name}: {str(exc).splitlines()[0][:160]}"]
    registry = registry or schema_registry()
    errors = []
    resolver = registry.resolver(base_uri=schema.get("$id", ""))
    for where, ref in iter_refs(schema):
        try:
            resolver.lookup(ref) if (ref.startswith("#") is False or schema.get("$id")) else _pointer(schema, ref)
        except Exception:
            errors.append(f"{path.name}:{where}: unresolved $ref {ref}")
    return errors


def validate_instance(schema_path, instance_path, registry=None):
    """Validate an example against a schema (used by example fixtures)."""
    schema = load(schema_path)
    v = Draft202012Validator(schema, registry=registry or schema_registry())
    return [f"{Path(instance_path).name}: {'/'.join(map(str, e.absolute_path))}: {e.message[:160]}"
            for e in v.iter_errors(load(instance_path))]


# ---------- overlay (ADR-009, ADR-038) ----------
def merge_overlay(base, overlay):
    """Additive-only merge: overlay may add keys; redefining an existing key with a different value is an error."""
    errors = []

    def walk(b, o, trail):
        for k, v in o.items():
            here = f"{trail}/{k}"
            if k not in b:
                b[k] = copy.deepcopy(v)
            elif isinstance(b[k], dict) and isinstance(v, dict):
                walk(b[k], v, here)
            elif b[k] != v:
                errors.append(f"overlay redefines existing {here}")

    merged = copy.deepcopy(base)
    walk(merged, overlay, "")
    return merged, errors


OVERLAY_ROOT_KEYS = {"openapi": {"paths", "components", "tags"}, "asyncapi": {"channels", "operations", "components"}}


def overlay_files(kind):
    d = CONTRACTS / kind / "extensions"
    if not d.is_dir():
        raise FileNotFoundError(f"{d} missing (overlay directory is required, ADR-009)")
    return sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))


def overlay_stray_files(kind):
    d = CONTRACTS / kind / "extensions"
    return [f"{kind}/extensions/{f.name}: unsupported overlay file (only *.yaml/*.yml and README.md)"
            for f in sorted(d.iterdir()) if f.name != "README.md" and f.suffix not in (".yaml", ".yml")]


def merged_document(kind, base_path):
    doc, errs = load(base_path), overlay_stray_files(kind)
    for f in overlay_files(kind):
        ov = load(f)
        if not isinstance(ov, dict):
            errs.append(f"{f.name}: empty or non-mapping overlay")
            continue
        if ov.get("x-status") != "WORKING":
            errs.append(f"{f.name}: overlay must declare x-status: WORKING")
        if not ov.get("x-source"):
            errs.append(f"{f.name}: overlay must declare x-source (normative references)")
        body = {k: v for k, v in ov.items() if k not in ("x-status", "x-source")}
        bad = set(body) - OVERLAY_ROOT_KEYS[kind]
        if bad:
            errs.append(f"{f.name}: overlay may only extend {sorted(OVERLAY_ROOT_KEYS[kind])}, found {sorted(bad)}")
            body = {k: v for k, v in body.items() if k in OVERLAY_ROOT_KEYS[kind]}
        doc, e = merge_overlay(doc, body)
        errs += [f"{f.name}: {x}" for x in e]
    return doc, errs


# ---------- breaking changes ----------
def deref(node, root, seen=()):
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#"):
            if ref in seen:
                return {"$cycle": ref}
            try:
                target = _pointer(root, ref)
            except KeyError:
                return {"$unresolved": ref}
            return deref(target, root, seen + (ref,))
        return {k: deref(v, root, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [deref(v, root, seen) for v in node]
    return node


def schema_breaks(old, new, direction, path):
    """direction: 'request' (clients send), 'response' (clients read), 'both' (conservative: any narrowing/removal)."""
    out = []
    if not isinstance(old, dict) or not isinstance(new, dict) or "$cycle" in old or "$cycle" in new:
        return out
    if "$unresolved" in old or "$unresolved" in new:
        return [f"{path}: unresolved $ref {old.get('$unresolved') or new.get('$unresolved')}"]
    if old.get("type") != new.get("type") and old.get("type") is not None:
        return [f"{path}: type {old.get('type')} -> {new.get('type')}"]
    if old.get("type") is None and new.get("type") is not None and direction != "response":
        out.append(f"{path}: type constraint added ({new.get('type')})")
    oe, ne = [str(x) for x in old.get("enum", [])], [str(x) for x in new.get("enum", [])]
    if oe and direction in ("request", "both") and set(oe) - set(ne):
        out.append(f"{path}: enum values removed {sorted(set(oe) - set(ne))}")
    if oe and direction in ("response", "both") and set(ne) - set(oe):
        out.append(f"{path}: enum values added {sorted(set(ne) - set(oe))}")
    if direction == "both" and set(oe) - set(ne) and not out:
        out.append(f"{path}: enum values removed {sorted(set(oe) - set(ne))}")
    if old.get("additionalProperties") is not False and new.get("additionalProperties") is False and direction != "response":
        out.append(f"{path}: additionalProperties became false")
    for key in ("properties", "$defs"):
        od, nd = old.get(key, {}), new.get(key, {})
        for name in od:
            here = f"{path}.{name}"
            if name not in nd:
                if key == "$defs" or direction in ("response", "both"):
                    out.append(f"{here}: {'definition' if key == '$defs' else 'property'} removed")
            else:
                out += schema_breaks(od[name], nd[name], direction, here)
    for key in ("oneOf", "anyOf", "allOf"):
        ol, nl = old.get(key, []), new.get(key, [])
        if len(nl) < len(ol) and key != "allOf":
            out.append(f"{path}: {key} branches removed ({len(ol)} -> {len(nl)})")
        for i, (x, y) in enumerate(zip(ol, nl)):
            out += schema_breaks(x, y, direction, f"{path}.{key}[{i}]")
        if key == "allOf" and len(nl) > len(ol) and direction != "response":
            out.append(f"{path}: allOf constraints added")
    for key in ("if", "then", "else", "not"):
        if key in old and key in new:
            out += schema_breaks(old[key], new[key], direction, f"{path}.{key}")
    oreq, nreq = set(old.get("required", [])), set(new.get("required", []))
    if direction in ("request", "both") and (nreq - oreq):
        out.append(f"{path}: new required {sorted(nreq - oreq)}")
    if direction in ("response", "both") and (oreq - nreq):
        out.append(f"{path}: required relaxed {sorted(oreq - nreq)}")
    if "items" in old and "items" in new:
        out += schema_breaks(old["items"], new["items"], direction, f"{path}[]")
    return out


def _json_schema_of(content):
    return (content or {}).get("application/json", {}).get("schema") or next(iter((content or {}).values()), {}).get("schema", {})


def breaking_openapi(old, new):
    old, new = deref(old, old), deref(new, new)
    out = []
    for p, ops in old.get("paths", {}).items():
        if p not in new.get("paths", {}):
            out.append(f"path removed: {p}")
            continue
        for m, op in ops.items():
            if m not in ("get", "post", "put", "patch", "delete"):
                continue
            nop = new["paths"][p].get(m)
            if nop is None:
                out.append(f"operation removed: {m.upper()} {p}")
                continue
            tag = f"{m.upper()} {p}"
            oparams = {(x["name"], x["in"]): x for x in ops.get("parameters", []) + op.get("parameters", [])}
            nparams = {(x["name"], x["in"]): x for x in new["paths"][p].get("parameters", []) + nop.get("parameters", [])}
            for k, x in nparams.items():
                if k not in oparams and x.get("required"):
                    out.append(f"{tag}: new required parameter {k[0]}")
                elif k in oparams and x.get("required") and not oparams[k].get("required"):
                    out.append(f"{tag}: parameter {k[0]} became required")
            for k in oparams:
                if k not in nparams:
                    out.append(f"{tag}: parameter removed {k[0]}")
            ob, nb = op.get("requestBody"), nop.get("requestBody")
            if nb and nb.get("required") and not (ob and ob.get("required")):
                out.append(f"{tag}: request body became required")
            if ob and not nb:
                out.append(f"{tag}: request body removed")
            if ob and nb:
                for ct in ob.get("content", {}):
                    if ct not in nb.get("content", {}):
                        out.append(f"{tag}: request content type removed {ct}")
                out += schema_breaks(_json_schema_of(ob.get("content")), _json_schema_of(nb.get("content")), "request", f"{tag} request")
            for code, r in op.get("responses", {}).items():
                nr = nop.get("responses", {}).get(code)
                if nr is None:
                    out.append(f"{tag}: response {code} removed")
                    continue
                out += schema_breaks(_json_schema_of(r.get("content")), _json_schema_of(nr.get("content")), "response", f"{tag} {code}")
    return out


def breaking_asyncapi(old, new):
    old, new = deref(old, old), deref(new, new)
    out = []
    for name in old.get("channels", {}):
        if name not in new.get("channels", {}):
            out.append(f"channel removed: {name}")
    for name, m in old.get("components", {}).get("messages", {}).items():
        nm = new.get("components", {}).get("messages", {}).get(name)
        if nm is None:
            out.append(f"message removed: {name}")
            continue
        out += schema_breaks(m.get("payload", {}), nm.get("payload", {}), "response", f"message {name}")
    return out


def breaking_jsonschema(old, new):
    return schema_breaks(deref(old, old), deref(new, new), "both", "schema")
