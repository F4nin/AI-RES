import datetime

import vuln_exceptions as ve

TODAY = datetime.date(2026, 11, 11)
GOOD = {"cve": "CVE-2026-0001", "component": "libx", "rationale": "r", "compensating_controls": "c", "owner": "o", "expires": "2027-01-01"}


def test_empty_file_has_no_exceptions():
    assert ve.parse("# c\nexceptions: []\n") == []


def test_valid_entry_passes():
    assert ve.validate([GOOD], TODAY) == []


def test_expired_entry_fails():
    assert any("expired" in e for e in ve.validate([{**GOOD, "expires": "2026-11-10"}], TODAY))


def test_missing_field_fails():
    assert any("missing" in e and "owner" in e for e in ve.validate([{k: v for k, v in GOOD.items() if k != "owner"}], TODAY))


def test_malformed_date_fails():
    assert any("malformed" in e for e in ve.validate([{**GOOD, "expires": "soon"}], TODAY))


def test_parse_list_of_entries():
    text = "exceptions:\n  - cve: CVE-1\n    component: a\n  - cve: CVE-2\n    component: b\n"
    assert [e["cve"] for e in ve.parse(text)] == ["CVE-1", "CVE-2"]


import pytest  # noqa: E402


def test_wrong_header_rejected():
    with pytest.raises(ValueError):
        ve.parse("exceptionz:\n  - cve: CVE-1\n")


def test_trailing_comment_is_not_part_of_value():
    assert ve.parse("exceptions:\n  - cve: CVE-1  # temporary\n    component: a\n")[0]["cve"] == "CVE-1"
