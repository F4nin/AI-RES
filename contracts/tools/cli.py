"""AI RES contracts CLI: `uv run python tools/cli.py <command>` (see Makefile target contracts-check)."""
import json
import subprocess
import sys

import contracts_lib as L

OAS = L.CONTRACTS / "openapi/AI_RES_Public_API_v1.3.yaml"
ASY = L.CONTRACTS / "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml"
SCHEMAS = sorted((L.CONTRACTS / "json-schema").rglob("*.json"))
BASELINE = L.CONTRACTS / "spectral-baseline.json"
MIN_SCHEMAS = 4


def cmd_verify_mirror():
    return L.verify_mirror()


def cmd_validate_openapi():
    errs = L.validate_openapi(OAS)
    doc, oerr = L.merged_document("openapi", OAS)
    return errs + oerr + _validate_merged_openapi(doc)


def _validate_merged_openapi(doc):
    from openapi_spec_validator import validate
    try:
        validate(doc)
        return []
    except Exception as exc:
        return [f"merged OpenAPI: {str(exc).splitlines()[0]}"]


def cmd_validate_asyncapi():
    doc, errs = L.merged_document("asyncapi", ASY)
    return L.validate_asyncapi(ASY) + errs + L.validate_asyncapi_doc(doc, "merged AsyncAPI")


def cmd_validate_jsonschema():
    if len(SCHEMAS) < MIN_SCHEMAS:
        return [f"expected at least {MIN_SCHEMAS} JSON files under json-schema/, found {len(SCHEMAS)}"]
    reg = L.schema_registry()
    return [e for f in SCHEMAS for e in L.validate_jsonschema(f, reg)]


def spectral_findings(path=OAS):
    """Run Spectral; any tool failure raises (the lint gate must never fail open)."""
    r = subprocess.run(["npx", "--no-install", "spectral", "lint", str(path), "-f", "json"], cwd=L.CONTRACTS,
                       capture_output=True, text=True)
    if r.returncode not in (0, 1) or not r.stdout.strip():
        raise RuntimeError(f"spectral failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[:300]}")
    return sorted({(x["code"], "/".join(map(str, x["path"])), x["severity"]) for x in json.loads(r.stdout)})


def cmd_lint_openapi():
    import tempfile
    doc, errs = L.merged_document("openapi", OAS)
    if errs:
        return errs
    spec = json.loads(BASELINE.read_text())
    base = {tuple(x) for x in spec["findings"]}
    with tempfile.TemporaryDirectory() as td:
        merged = L.Path(td) / "merged.yaml"
        merged.write_text(L.yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
        found = spectral_findings(merged)
    out = [f"new Spectral finding: {c} at {p} ({sev})" for c, p, sev in found if (c, p, sev) not in base]
    return out


def cmd_breaking(old_dir=None):
    """Compare current contracts (base + overlays) with the accepted snapshot in contracts/baseline/."""
    root = L.CONTRACTS / "baseline" if old_dir is None else L.Path(old_dir)
    needed = ["openapi/AI_RES_Public_API_v1.3.yaml", "asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml", "json-schema"]
    missing = [n for n in needed if not (root / n).exists()]
    if missing:
        return [f"baseline snapshot incomplete or missing: {missing}"]
    out = []
    for kind, fn, cur in (("openapi/AI_RES_Public_API_v1.3.yaml", L.breaking_openapi, OAS),
                          ("asyncapi/AI_RES_Domain_Events_AsyncAPI_v1.6.yaml", L.breaking_asyncapi, ASY)):
        doc, errs = L.merged_document(kind.split("/")[0], cur)
        out += errs + [f"{kind}: {b}" for b in fn(L.load(root / kind), doc)]
    old = {f.relative_to(root / "json-schema") for f in (root / "json-schema").rglob("*.json")}
    new = {f.relative_to(L.CONTRACTS / "json-schema") for f in SCHEMAS}
    out += [f"json-schema removed: {r}" for r in sorted(old - new)]
    for r in sorted(old & new):
        a_, b_ = L.load(root / "json-schema" / r), L.load(L.CONTRACTS / "json-schema" / r)
        if isinstance(a_, dict) and a_.get("$schema"):
            out += [f"{r.name}: {x}" for x in L.breaking_jsonschema(a_, b_)]
    return out


COMMANDS = {n[4:].replace("_", "-"): f for n, f in globals().items() if n.startswith("cmd_")}


def main(argv):
    names = argv[1:] or ["all"]
    if "all" in names:
        names = ["verify-mirror", "validate-openapi", "validate-asyncapi", "validate-jsonschema", "lint-openapi", "breaking"]
    unknown = [n for n in names if n not in COMMANDS]
    if unknown:
        print(f"unknown command(s) {unknown}; available: {sorted(COMMANDS)} or 'all'")
        return 2
    failed = False
    for n in names:
        try:
            errs = COMMANDS[n]()
        except Exception as exc:  # a crashing check is a failed check, never a pass
            errs = [f"{type(exc).__name__}: {exc}"]
        print(f"[{'FAIL' if errs else 'ok'}] {n}")
        for e in errs:
            print("   ", e)
        failed |= bool(errs)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
