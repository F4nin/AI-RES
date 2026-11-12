#!/usr/bin/env python3
"""Repository secret scan (Secrets & Key Management §8; layer-1 deterministic check, ADR-037). Scans every file git would commit
(tracked + untracked, minus ignored) except third-party ECC prose under .claude/. Fails on: private keys, age secret keys, well-known
token formats, credential-looking assignments with literal values (including JSON-quoted keys), credentials embedded in URLs, current
dev secret VALUES, unreadable files, and files in infra/secrets/encrypted/ that are not fully SOPS-encrypted. Never prints values."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_PREFIXES = (".claude/", "docs/implementation/reviews/")  # third-party ECC prose; review reports quote deliberately fake examples
KEY = r"""["']?[\w-]*(?:password|passwd|secret|api[_-]?key|token|private[_-]?key)[\w-]*["']?"""
RULES = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "age secret key": re.compile(r"AGE-SECRET-KEY-1[A-Z0-9]{20,}"),
    "known token format": re.compile(
        r"\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9_-]{20,})\b"
    ),
    "bearer token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{24,}={0,2}"),
    "credentials in URL": re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@$<{]+:(?![$<{])[^/\s@$<{]{6,}@[\w.-]+", re.I),
    # value: not a placeholder/path/reference/call, >= 16 chars of printable non-space; identifiers (lower snake/dotted, containing _ or .) are not secrets
    "literal secret assignment": re.compile(  # noqa: E501
        rf"""(?i){KEY}[ \t]*[:=][ \t]*["']?(?![./$<{{\[\s"']|ENC\[|/run/secrets|(?:true|false|none|null)\b)(?!(?-i:(?=[a-z0-9_.]*[_.])[a-z_][a-z0-9_.]*)["']?\s*(?:$|[,)#]))(?![\w.]*\()[^\s"',;]{{16,}}"""  # noqa: E501
    ),
}
SKIP_SUFFIX = {".png", ".jpg", ".gif", ".ico", ".pdf", ".lock", ".sum"}
ALLOW = {  # deliberately fake violations
    "infra/tests/test_scan_secrets.py",
    "backend/tests/unit/test_platform.py",
    "backend/tests/unit/test_telemetry_export.py",
}


def files(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root, capture_output=True, check=True).stdout  # noqa: S603, S607
    return [root / p for p in out.decode().split("\0") if p]


def runtime_values(root: Path) -> list[str]:
    d = root / "infra" / "secrets" / "runtime"
    vals = [p.read_text().strip() for p in d.iterdir() if p.is_file()] if d.is_dir() else []
    return [v for v in vals if len(v) >= 12]


def unencrypted_lines(body: str) -> list[str]:
    """Scalar values outside the `sops:` metadata block that are not SOPS ciphertext."""
    head = body.split("\nsops:", 1)[0]
    bad = []
    for ln in head.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        val = s[2:] if s.startswith("- ") else s.split(": ", 1)[1] if ": " in s else ("" if s.endswith(":") else s)
        if val.strip() and not val.strip().startswith("ENC["):
            bad.append(s)
    return bad


def scan(root: Path) -> list[str]:
    found: list[str] = []
    values = runtime_values(root)
    for f in files(root):
        rel = f.relative_to(root).as_posix()
        if rel.startswith(EXCLUDED_PREFIXES) or f.suffix in SKIP_SUFFIX or rel in ALLOW or not f.is_file():
            continue
        try:
            text = f.read_bytes().decode("utf-8", errors="replace")  # undecodable bytes are scanned, not skipped
        except OSError as exc:
            found.append(f"{rel}: unreadable ({type(exc).__name__}); cannot be scanned")
            continue
        for name, rx in RULES.items():
            for m in rx.finditer(text):
                found.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {name}")
        if any(v in text for v in values):
            found.append(f"{rel}: contains a current dev secret value")
        is_encrypted_file = rel.startswith("infra/secrets/encrypted/") and not rel.endswith(".gitkeep")
        if is_encrypted_file and ("\nsops:" not in text or "ENC[AES256_GCM" not in text or unencrypted_lines(text)):
            found.append(f"{rel}: not a SOPS-encrypted file with only encrypted values")
    return found


def main() -> int:
    found = scan(ROOT)
    for v in found:
        print(f"FOUND: {v}")
    print(f"{len(found)} finding(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
