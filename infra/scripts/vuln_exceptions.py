#!/usr/bin/env python3
"""Validates infra/security/vulnerability-exceptions.yaml (a tiny YAML subset: list of flat mappings under `exceptions:`) and prints the
CVE ids for Trivy's ignore file. Exits 1 on missing fields, expired entries or malformed dates. Stdlib only."""
import datetime
import re
import sys
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "security" / "vulnerability-exceptions.yaml"
REQUIRED = ("cve", "component", "rationale", "compensating_controls", "owner", "expires")


def parse(text: str) -> list[dict[str, str]]:
    body = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if not body or body[0].strip() not in ("exceptions:", "exceptions: []"):
        raise ValueError("file must start with 'exceptions:' (or 'exceptions: []')")
    if body[0].strip() == "exceptions: []":
        return []
    entries: list[dict[str, str]] = []
    for ln in body[1:]:
        ln = re.sub(r"\s+#.*$", "", ln)  # trailing comment is not part of the value
        m = re.match(r"^\s*(-\s+)?([a-z_]+):\s*(.+?)\s*$", ln)
        if not m:
            raise ValueError(f"unparsable line: {ln!r}")
        if m.group(1):
            entries.append({})
        entries[-1][m.group(2)] = m.group(3).strip("\"'")
    return entries


def validate(entries: list[dict[str, str]], today: datetime.date) -> list[str]:
    errs: list[str] = []
    for e in entries:
        miss = [k for k in REQUIRED if not e.get(k)]
        if miss:
            errs.append(f"{e.get('cve', '?')}: missing {', '.join(miss)}")
            continue
        try:
            if datetime.date.fromisoformat(e["expires"]) < today:
                errs.append(f"{e['cve']}: exception expired on {e['expires']}")
        except ValueError:
            errs.append(f"{e['cve']}: malformed expires {e['expires']!r}")
    return errs


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "ids"
    entries = parse(FILE.read_text())
    errs = validate(entries, datetime.date.today())
    for e in errs:
        print(f"EXCEPTION ERROR: {e}", file=sys.stderr)
    if errs:
        return 1
    if mode == "ids":
        print("\n".join(e["cve"] for e in entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
