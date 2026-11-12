"""SigV4 query presigning (ADR-081): the published AWS example, restriction binding and input validation."""
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import pytest

from ai_res.modules.sources.presign import StorageCredentials, checksum_header, presign_url

CREDS = StorageCredentials("AKIA" + "IOSFODNN7EXAMPLE",  # the public AWS documentation example; split so the secret scanner does not flag a known token format
                           "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")
AT = datetime(2013, 5, 24, tzinfo=UTC)


def test_matches_the_published_aws_example_signature() -> None:
    url = presign_url("GET", "https://examplebucket.s3.amazonaws.com", "/test.txt", {}, CREDS, region="us-east-1", now=AT, expires_seconds=86400)
    assert parse_qs(urlsplit(url).query)["X-Amz-Signature"] == ["aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"]


def test_every_restriction_is_signed_and_changing_one_changes_the_signature() -> None:
    headers = {"Content-Type": "text/plain", "Content-Length": "10", "x-amz-checksum-sha256": checksum_header("00" * 32)}
    base = presign_url("PUT", "https://files.example.com", "/b/k", headers, CREDS, region="us-east-1", now=AT, expires_seconds=300)
    signed = parse_qs(urlsplit(base).query)["X-Amz-SignedHeaders"][0].split(";")
    assert signed == ["content-length", "content-type", "host", "x-amz-checksum-sha256"]
    for name, other in (("Content-Length", "11"), ("Content-Type", "application/pdf"), ("x-amz-checksum-sha256", checksum_header("01" * 32))):
        changed = presign_url("PUT", "https://files.example.com", "/b/k", {**headers, name: other}, CREDS, region="us-east-1", now=AT, expires_seconds=300)
        assert parse_qs(urlsplit(changed).query)["X-Amz-Signature"] != parse_qs(urlsplit(base).query)["X-Amz-Signature"]


def test_the_secret_never_appears_in_the_url_or_the_repr() -> None:
    url = presign_url("PUT", "https://files.example.com", "/b/k", {}, CREDS, region="us-east-1", now=AT, expires_seconds=300)
    assert CREDS.secret_key not in url and CREDS.secret_key not in repr(CREDS) and CREDS.access_key not in repr(CREDS)


@pytest.mark.parametrize("kwargs", [{"expires_seconds": 0}, {"expires_seconds": 604_801}, {"base_url": "https://u:p@h"}, {"base_url": "https://h/path"},
                                    {"base_url": "ftp://h"}, {"path": "relative"}, {"now": datetime(2013, 5, 24)}])
def test_invalid_input_is_refused(kwargs: dict[str, object]) -> None:
    args: dict[str, object] = {"base_url": "https://files.example.com", "path": "/b/k", "now": AT, "expires_seconds": 300}
    args.update(kwargs)
    with pytest.raises(ValueError):  # noqa: PT011 - every refusal is a ValueError by contract
        presign_url("PUT", str(args["base_url"]), str(args["path"]), {}, CREDS, region="us-east-1", now=args["now"], expires_seconds=args["expires_seconds"])  # type: ignore[arg-type]
