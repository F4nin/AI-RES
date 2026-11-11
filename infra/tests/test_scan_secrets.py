"""The repository secret scan must fail on intentional violations (ADR-037 layer 1) and pass on clean trees."""
import subprocess

import scan_secrets as ss


def repo(tmp_path, files: dict[str, str]):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return tmp_path


def test_clean_tree_passes(tmp_path):
    assert ss.scan(repo(tmp_path, {"infra/a.py": "x = 1\nPASSWORD_FILE=/run/secrets/pg\n", "infra/b.yaml": "password: ${PW}\n"})) == []


def test_private_key_detected(tmp_path):
    assert any("private key" in f for f in ss.scan(repo(tmp_path, {"infra/k.txt": "-----BEGIN RSA PRIVATE KEY-----\nabc\n"})))


def test_age_secret_key_detected(tmp_path):
    assert any("age secret key" in f for f in ss.scan(repo(tmp_path, {"infra/k.txt": "AGE-SECRET-KEY-1" + "Q" * 40})))


def test_literal_password_assignment_detected(tmp_path):
    assert any("literal secret" in f for f in ss.scan(repo(tmp_path, {"infra/c.env": "DB_PASSWORD=Sup3rS3cretValue12345\n"})))


def test_credentials_in_url_detected(tmp_path):
    assert any("URL" in f for f in ss.scan(repo(tmp_path, {"infra/c.py": 'u = "postgresql://app:hunter2hunter2@db:5432/x"\n'})))


def test_current_dev_secret_value_detected(tmp_path):
    t = repo(tmp_path, {"infra/secrets/runtime/pw": "ZZZtopSecretValue987654", "infra/notes.md": "token ZZZtopSecretValue987654\n"})
    assert any("infra/notes.md" in f and "dev secret value" in f for f in ss.scan(t))


def test_plaintext_file_in_encrypted_dir_detected(tmp_path):
    assert any("not a SOPS" in f for f in ss.scan(repo(tmp_path, {"infra/secrets/encrypted/x.enc.yaml": "db_password: plainvalue\n"})))


def test_sops_encrypted_file_accepted(tmp_path):
    body = "db_password: ENC[AES256_GCM,data:abc,iv:x,tag:y,type:str]\nsops:\n    age:\n        - recipient: age1abc\n"
    assert ss.scan(repo(tmp_path, {"infra/secrets/encrypted/x.enc.yaml": body})) == []


def test_json_quoted_key_detected(tmp_path):
    assert any("literal secret" in f for f in ss.scan(repo(tmp_path, {"infra/c.json": '{"db_password": "Zx9!kQ-LetterOnlyAndSymbols"}'})))


def test_special_char_and_letter_only_passwords_detected(tmp_path):
    t = repo(tmp_path, {"infra/a.env": "API_TOKEN=Abc!defGhi%jklMno-pqr\n", "infra/b.env": "ROOT_PASSWORD=abcdefghijklmnopqrstuvwxyzABC\n"})
    assert len([f for f in ss.scan(t) if "literal secret" in f]) == 2


def test_known_token_formats_detected(tmp_path):
    t = repo(tmp_path, {"infra/a.txt": "key AKIAABCDEFGHIJKLMNOP\n", "infra/b.txt": "ghp_" + "a" * 36 + "\n", "infra/c.txt": "Authorization: Bearer " + "x" * 30 + "\n"})
    assert len(ss.scan(t)) == 3


def test_identifiers_and_paths_are_not_flagged(tmp_path):
    body = "secret = read_secret_file(settings.cursor_hmac_key_file)\ncursor_hmac_key_file: Path | None = None\nPASSWORD_FILE: /run/secrets/postgres_pw\n"
    assert ss.scan(repo(tmp_path, {"infra/a.py": body})) == []


def test_root_level_files_are_scanned(tmp_path):
    assert any(".env" in f for f in ss.scan(repo(tmp_path, {".env": "DB_PASSWORD=Sup3rS3cretValue12345\n"})))


def test_non_utf8_file_is_still_scanned(tmp_path):
    t = repo(tmp_path, {})
    (t / "infra").mkdir()
    (t / "infra" / "bin.cfg").write_bytes(b"\xff\xfe DB_PASSWORD=Sup3rS3cretValue12345\n")
    assert any("literal secret" in f for f in ss.scan(t))


def test_trailing_newline_in_dev_secret_file_still_matches(tmp_path):
    t = repo(tmp_path, {"infra/secrets/runtime/pw": "ZZZtopSecretValue987654\n", "infra/notes.md": "x ZZZtopSecretValue987654 y\n"})
    assert any("dev secret value" in f for f in ss.scan(t))


def test_sops_file_with_one_encrypted_value_and_nested_plaintext_rejected(tmp_path):
    body = "a: ENC[AES256_GCM,data:abc]\nnested:\n    inner: plainvalue\nsops:\n    age: []\n"
    assert any("not a SOPS" in f for f in ss.scan(repo(tmp_path, {"infra/secrets/encrypted/x.enc.yaml": body})))


def test_lowercase_alphanumeric_secrets_without_separators_detected(tmp_path):
    t = repo(
        tmp_path,
        {
            "infra/a.env": 'api_key="a1b2c3d4e5f60718293a4b5c6d7e8f90"\n',
            "infra/b.yaml": "secret: abcdefghijklmnopqrstuvwxyz\n",
            "infra/c.env": "DB_PASSWORD=correcthorsebatterystaple\n",
        },
    )
    assert len([f for f in ss.scan(t) if "literal secret" in f]) == 3
